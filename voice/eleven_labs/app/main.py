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
from datetime import datetime
from typing import Optional
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
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Static 파일 서빙
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


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


@app.get("/")
async def root():
    """메인 페이지 - static/index.html 반환"""
    return FileResponse("static/index.html")


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

        with open(filepath, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)

        return TTSResponse(
            success=True,
            audio_url=f"/audio/{filename}",
            filename=filename
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
