from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import torch
import torchaudio
import os
import uuid
import time
import asyncio
import traceback
from datetime import datetime
from pathlib import Path

from zonos.model import Zonos
from zonos.conditioning import make_cond_dict
from zonos.utils import DEFAULT_DEVICE as device

# FastAPI 앱 초기화
app = FastAPI(title="Zonos TTS API", version="1.0.0")

# CORS 설정 (Flutter 웹 앱에서 접근 가능하도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PyTorch 컴파일 비활성화
torch._dynamo.config.suppress_errors = True
import torch._dynamo
torch._dynamo.reset()

# 전역 모델 변수 (한 번만 로드)
model = None
default_speaker = None

# 출력 디렉토리
OUTPUT_DIR = "generated_audio"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 파일 자동 삭제 설정 (시간 단위)
FILE_MAX_AGE_HOURS = 1


def cleanup_old_files(directory: str, max_age_hours: int = FILE_MAX_AGE_HOURS):
    """오래된 파일 삭제"""
    now = time.time()
    deleted_count = 0
    for file in Path(directory).glob("*"):
        if file.is_file() and file.suffix in ['.wav', '.mp3']:
            age_hours = (now - file.stat().st_mtime) / 3600
            if age_hours > max_age_hours:
                try:
                    file.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"파일 삭제 실패 {file}: {e}")
    if deleted_count > 0:
        print(f"[Cleanup] {deleted_count}개 오래된 파일 삭제됨")


async def periodic_cleanup():
    """주기적으로 오래된 파일 삭제 (30분마다)"""
    while True:
        await asyncio.sleep(1800)  # 30분
        cleanup_old_files(OUTPUT_DIR)


class TTSRequest(BaseModel):
    """TTS 요청 모델"""
    text: str = Field(..., description="생성할 텍스트")
    language: str = Field("ko", description="언어 코드 (ko, en-us, ja 등)")

    # 감정 파라미터
    emotion: Optional[List[float]] = Field(
        None,
        description="감정 벡터 [행복, 슬픔, 혐오, 두려움, 놀람, 분노, 기타, 중립]"
    )

    # 음성 특성 파라미터
    fmax: float = Field(22050.0, description="최대 주파수 (22050 또는 24000)")
    pitch_std: float = Field(20.0, description="음높이 표준편차 (20-45: 일반, 60-150: 표현력)")
    speaking_rate: float = Field(15.0, description="말하는 속도 (10: 느림, 15: 보통, 30: 빠름)")

    # 생성 파라미터
    max_new_tokens: int = Field(86 * 30, description="최대 생성 토큰 수")
    cfg_scale: float = Field(2.0, description="CFG 스케일 (1.0~3.0)")
    min_p: float = Field(0.1, description="샘플링 min_p 파라미터")

    # 화자 설정
    speaker_audio_path: Optional[str] = Field(None, description="화자 음성 파일 경로")


class TTSResponse(BaseModel):
    """TTS 응답 모델"""
    success: bool
    audio_file: str
    message: str
    settings: dict


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 모델 로드"""
    global model, default_speaker

    print("모델 로딩 중...")
    model = Zonos.from_pretrained("Zyphra/Zonos-v0.1-transformer", device=device)

    # 기본 화자 임베딩 로드 (있는 경우)
    default_speaker_path = "assets/Ref_IU_Original_Voice.wav"
    if os.path.exists(default_speaker_path):
        wav, sampling_rate = torchaudio.load(default_speaker_path)
        print(f"[DEBUG] WAV shape: {wav.shape}, sample_rate: {sampling_rate}")
        default_speaker = model.make_speaker_embedding(wav, sampling_rate)
        print(f"[DEBUG] Default speaker shape: {default_speaker.shape}")
        print(f"[DEBUG] Default speaker dtype: {default_speaker.dtype}")
        print(f"[DEBUG] Default speaker device: {default_speaker.device}")
        print(f"기본 화자 임베딩 로드 완료: {default_speaker_path}")

    print("모델 로딩 완료!")
    
    # 시작 시 오래된 파일 정리
    cleanup_old_files(OUTPUT_DIR)
    
    # 백그라운드 정리 태스크 시작
    asyncio.create_task(periodic_cleanup())
    print(f"[Cleanup] 자동 파일 정리 활성화 ({FILE_MAX_AGE_HOURS}시간 이상 파일 삭제)")


@app.get("/")
async def root():
    """API 루트 엔드포인트"""
    return {
        "message": "Zonos TTS API",
        "version": "1.0.0",
        "endpoints": {
            "POST /generate": "음성 생성",
            "GET /audio/{filename}": "생성된 오디오 다운로드",
            "GET /health": "헬스 체크"
        }
    }


@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "device": str(device)
    }


@app.post("/generate", response_model=TTSResponse)
async def generate_speech(request: TTSRequest):
    """
    텍스트를 음성으로 변환

    - **text**: 생성할 텍스트 (필수)
    - **language**: 언어 코드 (기본값: ko)
    - **emotion**: 감정 벡터 (선택, 8개 값)
    - **pitch_std**: 음높이 변화 (20-45: 일반, 60-150: 표현력)
    - **speaking_rate**: 말하는 속도 (10: 느림, 15: 보통, 30: 빠름)
    """
    try:
        if model is None:
            raise HTTPException(status_code=503, detail="모델이 로드되지 않았습니다")

        # 화자 임베딩 결정
        if request.speaker_audio_path and os.path.exists(request.speaker_audio_path):
            wav, sampling_rate = torchaudio.load(request.speaker_audio_path)
            speaker = model.make_speaker_embedding(wav, sampling_rate)
        elif default_speaker is not None:
            speaker = default_speaker
        else:
            raise HTTPException(
                status_code=400,
                detail="화자 임베딩이 없습니다. speaker_audio_path를 제공하거나 기본 화자를 설정하세요."
            )

        # 기본 감정 벡터 (중립)
        emotion = request.emotion or [0.3077, 0.0256, 0.0256, 0.0256, 0.0256, 0.0256, 0.2564, 0.3077]

        # 디버깅: speaker embedding 정보 출력
        print(f"[DEBUG] Speaker shape: {speaker.shape if speaker is not None else None}")
        print(f"[DEBUG] Speaker dtype: {speaker.dtype if speaker is not None else None}")
        print(f"[DEBUG] Speaker device: {speaker.device if speaker is not None else None}")
        print(f"[DEBUG] Model device: {device}")

        # 조건 딕셔너리 생성 (명시적으로 device 전달)
        cond_dict = make_cond_dict(
            text=request.text,
            speaker=speaker,
            language=request.language,
            emotion=emotion,
            fmax=request.fmax,
            pitch_std=request.pitch_std,
            speaking_rate=request.speaking_rate,
            device=device,
        )

        # 디버깅: cond_dict 키와 shape 출력
        for k, v in cond_dict.items():
            if isinstance(v, torch.Tensor):
                print(f"[DEBUG] cond_dict[{k}]: shape={v.shape}, dtype={v.dtype}, device={v.device}")

        # 조건 준비
        conditioning = model.prepare_conditioning(cond_dict)

        # 음성 생성
        codes = model.generate(
            conditioning,
            max_new_tokens=request.max_new_tokens,
            cfg_scale=request.cfg_scale,
            sampling_params={"min_p": request.min_p},
        )

        # 디코딩
        wavs = model.autoencoder.decode(codes).cpu()

        # 파일 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"tts_{timestamp}_{unique_id}.wav"
        filepath = os.path.join(OUTPUT_DIR, filename)

        torchaudio.save(filepath, wavs[0], model.autoencoder.sampling_rate)

        return TTSResponse(
            success=True,
            audio_file=filename,
            message="음성 생성 완료",
            settings={
                "text": request.text,
                "language": request.language,
                "speaking_rate": request.speaking_rate,
                "pitch_std": request.pitch_std,
                "cfg_scale": request.cfg_scale,
            }
        )

    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"[ERROR] 음성 생성 실패:\n{error_detail}")
        raise HTTPException(status_code=500, detail=f"음성 생성 실패: {str(e)}\n{error_detail}")


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """생성된 오디오 파일 다운로드"""
    filepath = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    return FileResponse(
        filepath,
        media_type="audio/wav",
        filename=filename
    )


@app.delete("/audio/{filename}")
async def delete_audio(filename: str):
    """생성된 오디오 파일 삭제"""
    filepath = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    os.remove(filepath)
    return {"success": True, "message": f"{filename} 삭제 완료"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
