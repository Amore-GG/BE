"""
ElevenLabs TTS FastAPI Server

사용법:
uvicorn app.main:app --reload --host 0.0.0.0 --port 1100
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from elevenlabs.client import ElevenLabs
from elevenlabs.types import VoiceSettings
import os
import time
import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path
import io

app = FastAPI(
    title="ElevenLabs TTS API",
    description="Text-to-Speech API using ElevenLabs",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 환경 변수 또는 기본값
API_KEY = os.environ.get("ELEVENLABS_API_KEY", "sk_81a58227f843864721833e1b1dee9cbb66312f7234247bbc")
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "8jHHF8rMqMlg8if2mOUe")
MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

# 오디오 저장 폴더
OUTPUT_DIR = "generated_audio"
SHARED_DIR = "shared"  # 세션 기반 공유 폴더 (상위)
SHARED_TTS_DIR = "shared/tts"  # 일반 TTS 공유 폴더
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)
os.makedirs(SHARED_TTS_DIR, exist_ok=True)


def get_session_dir(session_id: str) -> str:
    """세션 디렉토리 경로 반환 (없으면 생성)"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir

# 파일 자동 삭제 설정 (시간 단위)
FILE_MAX_AGE_HOURS = 3


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
        cleanup_old_files(SHARED_TTS_DIR)


# Static 파일 서빙
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    # 시작 시 오래된 파일 정리
    cleanup_old_files(OUTPUT_DIR)
    cleanup_old_files(SHARED_TTS_DIR)
    
    # 백그라운드 정리 태스크 시작
    asyncio.create_task(periodic_cleanup())
    print(f"[Cleanup] 자동 파일 정리 활성화 ({FILE_MAX_AGE_HOURS}시간 이상 파일 삭제)")
    print(f"[Shared] 일반 TTS: {SHARED_TTS_DIR}")
    print(f"[Shared] 세션 기반 TTS: {SHARED_DIR}/{{session_id}}/")


class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    stability: Optional[float] = 0.8
    similarity_boost: Optional[float] = 0.8
    style: Optional[float] = 0.4
    use_speaker_boost: Optional[bool] = True


class TTSResponse(BaseModel):
    success: bool
    audio_url: str
    filename: str
    shared_path: str  # 다른 서비스에서 접근 가능한 경로


class SessionTTSRequest(BaseModel):
    """세션 기반 TTS 요청"""
    session_id: str  # 세션 ID (필수)
    text: str  # 생성할 텍스트 (필수)
    output_filename: Optional[str] = "tts_audio.mp3"  # 저장할 파일명
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    stability: Optional[float] = 0.8
    similarity_boost: Optional[float] = 0.8
    style: Optional[float] = 0.4
    use_speaker_boost: Optional[bool] = True


class SessionTTSResponse(BaseModel):
    """세션 기반 TTS 응답"""
    success: bool
    session_id: str
    filename: str
    session_path: str  # 세션 폴더 내 경로
    message: str


@app.get("/")
async def root():
    """API 루트"""
    return {
        "message": "ElevenLabs TTS API",
        "version": "1.0.0",
        "endpoints": {
            "POST /generate": "TTS 생성 (일반)",
            "POST /session/generate": "TTS 생성 (세션 기반)",
            "GET /audio/{filename}": "오디오 파일 다운로드",
            "GET /session/{session_id}/files": "세션 내 파일 목록",
            "GET /session/{session_id}/audio/{filename}": "세션 내 오디오 다운로드",
            "GET /health": "헬스 체크"
        }
    }


@app.get("/health")
async def health_check():
    """서버 상태 체크"""
    return {"status": "ok"}


@app.post("/generate", response_model=TTSResponse)
async def generate_tts(request: TTSRequest):
    """
    TTS 생성 (POST) - 파일로 저장 후 URL 반환
    """
    try:
        if not request.text:
            raise HTTPException(status_code=400, detail="텍스트가 비어있습니다")

        voice_id = request.voice_id or VOICE_ID
        model_id = request.model_id or MODEL_ID

        # ElevenLabs 클라이언트
        client = ElevenLabs(api_key=API_KEY)

        # Voice Settings
        voice_settings = VoiceSettings(
            stability=request.stability,
            similarity_boost=request.similarity_boost,
            style=request.style,
            use_speaker_boost=request.use_speaker_boost
        )

        # TTS 생성
        audio_stream = client.text_to_speech.convert(
            text=request.text,
            voice_id=voice_id,
            model_id=model_id,
            voice_settings=voice_settings,
        )

        # 파일 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tts_{timestamp}.mp3"
        filepath = os.path.join(OUTPUT_DIR, filename)
        shared_filepath = os.path.join(SHARED_TTS_DIR, filename)

        # 오디오 데이터를 메모리에 먼저 저장
        audio_data = b""
        for chunk in audio_stream:
            audio_data += chunk

        # 기본 폴더에 저장
        with open(filepath, "wb") as f:
            f.write(audio_data)

        # shared 폴더에도 저장 (다른 서비스에서 접근 가능)
        with open(shared_filepath, "wb") as f:
            f.write(audio_data)

        return TTSResponse(
            success=True,
            audio_url=f"/audio/{filename}",
            filename=filename,
            shared_path=f"/app/shared/tts/{filename}"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tts")
async def tts_simple(text: str = Query(..., description="변환할 텍스트")):
    """
    간단한 TTS (GET) - 바로 오디오 스트림 반환
    index.html에서 사용
    """
    try:
        if not text:
            raise HTTPException(status_code=400, detail="텍스트가 비어있습니다")

        client = ElevenLabs(api_key=API_KEY)

        voice_settings = VoiceSettings(
            stability=0.8,
            similarity_boost=0.8,
            style=0.4,
            use_speaker_boost=True
        )

        audio_stream = client.text_to_speech.convert(
            text=text,
            voice_id=VOICE_ID,
            model_id=MODEL_ID,
            voice_settings=voice_settings,
        )

        # 오디오 데이터를 메모리에 저장
        audio_data = b""
        for chunk in audio_stream:
            audio_data += chunk

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=tts.mp3"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """저장된 오디오 파일 반환"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="File not found")


# ============================================
# 세션 기반 엔드포인트
# ============================================
@app.post("/session/generate", response_model=SessionTTSResponse, tags=["Session"])
async def session_generate_tts(request: SessionTTSRequest):
    """
    세션 기반 TTS 생성
    
    결과 오디오가 세션 폴더에 저장됩니다.
    다른 서비스(z_image, i2v 등)에서 동일한 session_id로 접근 가능합니다.
    """
    try:
        if not request.text:
            raise HTTPException(status_code=400, detail="텍스트가 비어있습니다")

        session_dir = get_session_dir(request.session_id)
        
        voice_id = request.voice_id or VOICE_ID
        model_id = request.model_id or MODEL_ID

        # ElevenLabs 클라이언트
        client = ElevenLabs(api_key=API_KEY)

        # Voice Settings
        voice_settings = VoiceSettings(
            stability=request.stability,
            similarity_boost=request.similarity_boost,
            style=request.style,
            use_speaker_boost=request.use_speaker_boost
        )

        # TTS 생성
        audio_stream = client.text_to_speech.convert(
            text=request.text,
            voice_id=voice_id,
            model_id=model_id,
            voice_settings=voice_settings,
        )

        # 오디오 데이터를 메모리에 먼저 저장
        audio_data = b""
        for chunk in audio_stream:
            audio_data += chunk

        # 파일명 설정
        output_filename = request.output_filename or "tts_audio.mp3"
        if not output_filename.endswith(".mp3"):
            output_filename += ".mp3"
        
        # 세션 폴더에 저장
        session_filepath = os.path.join(session_dir, output_filename)
        with open(session_filepath, "wb") as f:
            f.write(audio_data)

        return SessionTTSResponse(
            success=True,
            session_id=request.session_id,
            filename=output_filename,
            session_path=f"/app/shared/{request.session_id}/{output_filename}",
            message=f"세션 '{request.session_id}'에 TTS 저장 완료"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/{session_id}/files", tags=["Session"])
async def list_session_files(session_id: str):
    """세션 폴더 내 파일 목록 조회"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    
    if not os.path.exists(session_dir):
        return {"session_id": session_id, "files": [], "count": 0, "exists": False}
    
    files = []
    for f in Path(session_dir).glob("*"):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
    files.sort(key=lambda x: x["created"], reverse=True)
    
    return {"session_id": session_id, "files": files, "count": len(files), "exists": True}


@app.get("/session/{session_id}/audio/{filename}", tags=["Session"])
async def get_session_audio(session_id: str, filename: str):
    """세션 폴더 내 오디오 파일 다운로드"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    filepath = os.path.join(session_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    return FileResponse(filepath, media_type="audio/mpeg", filename=filename)


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("ElevenLabs TTS FastAPI Server")
    print("=" * 60)
    print("Server running on: http://localhost:1100")
    print("API docs: http://localhost:1100/docs")
    print(f"Audio files saved to: {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=1100)
