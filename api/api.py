"""
Merge API
비디오/오디오 합치기 전용 API
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import uuid
import time
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path

# ============================================
# FastAPI 앱 초기화
# ============================================
app = FastAPI(
    title="Merge API",
    description="비디오/오디오 합치기 전용 API (FFmpeg 기반)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# 설정
# ============================================
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
SHARED_DIR = "shared"  # 공유 볼륨 (다른 서비스와 공유)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)

FILE_MAX_AGE_HOURS = 2
SESSION_MAX_AGE_HOURS = 24  # 세션 폴더는 24시간 유지


# ============================================
# 유틸리티 함수
# ============================================
def cleanup_old_files(directory: str, max_age_hours: int = FILE_MAX_AGE_HOURS):
    """오래된 파일 삭제"""
    now = time.time()
    deleted_count = 0
    for file in Path(directory).glob("*"):
        if file.is_file():
            age_hours = (now - file.stat().st_mtime) / 3600
            if age_hours > max_age_hours:
                try:
                    file.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"파일 삭제 실패 {file}: {e}")
    if deleted_count > 0:
        print(f"[Cleanup] {directory}: {deleted_count}개 오래된 파일 삭제됨")


async def periodic_cleanup():
    """주기적으로 오래된 파일 삭제"""
    while True:
        await asyncio.sleep(1800)
        cleanup_old_files(OUTPUT_DIR)
        cleanup_old_files(UPLOAD_DIR)


def get_media_duration(filepath: str) -> float:
    """미디어 파일의 길이(초) 반환"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return float(result.stdout.strip())
    return 0.0


def get_session_dir(session_id: str) -> str:
    """세션 디렉토리 경로 반환 (없으면 생성)"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def find_file_in_session(session_id: str, filename: str) -> str:
    """세션 폴더에서 파일 찾기"""
    session_dir = get_session_dir(session_id)
    filepath = os.path.join(session_dir, filename)
    if os.path.exists(filepath):
        return filepath
    raise FileNotFoundError(f"세션 '{session_id}'에서 파일을 찾을 수 없습니다: {filename}")


def cleanup_old_sessions(max_age_hours: int = SESSION_MAX_AGE_HOURS):
    """오래된 세션 폴더 삭제"""
    import shutil
    now = time.time()
    deleted_count = 0
    for session_dir in Path(SHARED_DIR).iterdir():
        if session_dir.is_dir():
            age_hours = (now - session_dir.stat().st_mtime) / 3600
            if age_hours > max_age_hours:
                try:
                    shutil.rmtree(session_dir)
                    deleted_count += 1
                except Exception as e:
                    print(f"세션 폴더 삭제 실패 {session_dir}: {e}")
    if deleted_count > 0:
        print(f"[Cleanup] {SHARED_DIR}: {deleted_count}개 오래된 세션 삭제됨")


# ============================================
# Pydantic 모델
# ============================================
class MergeVideosRequest(BaseModel):
    """비디오 연결 요청"""
    video_files: List[str] = Field(..., description="합칠 비디오 파일명 목록 (순서대로)")
    output_filename: Optional[str] = Field(None, description="출력 파일명")


class MergeAudioVideoRequest(BaseModel):
    """오디오+비디오 합치기 요청"""
    video_filename: str = Field(..., description="비디오 파일명")
    audio_filename: str = Field(..., description="오디오 파일명")
    output_filename: Optional[str] = Field(None, description="출력 파일명")


class AudioMixRequest(BaseModel):
    """오디오 믹싱 요청"""
    video_filename: str = Field(..., description="비디오 파일명 (기존 오디오 포함)")
    audio_filename: str = Field(..., description="추가할 오디오 파일명")
    video_volume: Optional[float] = Field(1.0, description="비디오 오디오 볼륨 (0.0~2.0)")
    audio_volume: Optional[float] = Field(0.3, description="추가 오디오 볼륨 (0.0~2.0)")
    output_filename: Optional[str] = Field(None, description="출력 파일명")


# === 세션 기반 요청 모델 ===
class SessionAudioVideoRequest(BaseModel):
    """세션 기반 오디오+비디오 합치기 요청"""
    session_id: str = Field(..., description="세션 ID (공유 폴더 내 하위 폴더)")
    video_filename: str = Field(..., description="비디오 파일명 (세션 폴더 내)")
    audio_filename: str = Field(..., description="오디오 파일명 (세션 폴더 내)")
    output_filename: Optional[str] = Field("merged.mp4", description="출력 파일명")


class SessionAudioMixRequest(BaseModel):
    """세션 기반 오디오 믹싱 요청"""
    session_id: str = Field(..., description="세션 ID (공유 폴더 내 하위 폴더)")
    video_filename: str = Field(..., description="비디오 파일명 (기존 오디오 포함)")
    audio_filename: str = Field(..., description="추가할 오디오 파일명")
    video_volume: Optional[float] = Field(1.0, description="비디오 오디오 볼륨 (0.0~2.0)")
    audio_volume: Optional[float] = Field(0.3, description="추가 오디오 볼륨 (0.0~2.0)")
    output_filename: Optional[str] = Field("final.mp4", description="출력 파일명")


class SessionMergeVideosRequest(BaseModel):
    """세션 기반 비디오 연결 요청"""
    session_id: str = Field(..., description="세션 ID")
    video_files: List[str] = Field(..., description="합칠 비디오 파일명 목록 (순서대로)")
    output_filename: Optional[str] = Field("merged.mp4", description="출력 파일명")


class MergeResponse(BaseModel):
    """합치기 응답"""
    success: bool
    output_file: str
    duration: float = Field(description="결과 영상 길이 (초)")
    message: str
    session_id: Optional[str] = Field(None, description="세션 ID (세션 기반 요청시)")


class UploadResponse(BaseModel):
    """업로드 응답"""
    success: bool
    filename: str
    file_type: str
    message: str
    session_id: Optional[str] = Field(None, description="세션 ID (세션 기반 업로드시)")


# ============================================
# 이벤트 핸들러
# ============================================
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    print("Merge API 시작...")
    print(f"Upload 디렉토리: {UPLOAD_DIR}")
    print(f"Output 디렉토리: {OUTPUT_DIR}")
    print(f"Shared 디렉토리: {SHARED_DIR}")
    
    cleanup_old_files(OUTPUT_DIR)
    cleanup_old_files(UPLOAD_DIR)
    cleanup_old_sessions()
    
    asyncio.create_task(periodic_cleanup())
    print(f"[Cleanup] 자동 파일 정리 활성화 ({FILE_MAX_AGE_HOURS}시간 이상 파일 삭제)")
    print(f"[Cleanup] 세션 폴더 자동 정리 활성화 ({SESSION_MAX_AGE_HOURS}시간 이상 세션 삭제)")
    
    # FFmpeg 확인
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("FFmpeg 확인됨")
        else:
            print("경고: FFmpeg를 찾을 수 없습니다!")
    except:
        print("경고: FFmpeg를 찾을 수 없습니다!")


# ============================================
# API 엔드포인트 - 기본
# ============================================
@app.get("/", tags=["Root"])
async def root():
    """API 루트"""
    return {
        "message": "Merge API",
        "version": "1.0.0",
        "description": "비디오/오디오 합치기 전용 API (공유 볼륨 지원)",
        "endpoints": {
            "일반 업로드": {
                "POST /upload/video": "비디오 업로드",
                "POST /upload/audio": "오디오 업로드",
            },
            "일반 합치기": {
                "POST /merge/videos": "비디오 여러개 연결",
                "POST /merge/audio-video": "무음 영상 + 오디오 합치기",
                "POST /merge/audio-mix": "영상(오디오있음) + 추가 오디오 믹싱",
            },
            "세션 기반 (공유 볼륨)": {
                "POST /session/upload": "세션 폴더에 파일 업로드",
                "GET /session/{session_id}/files": "세션 폴더 파일 목록",
                "GET /session/{session_id}/file/{filename}": "세션 파일 다운로드",
                "POST /session/merge/audio-video": "세션 내 비디오+오디오 합치기",
                "POST /session/merge/audio-mix": "세션 내 오디오 믹싱",
                "POST /session/merge/videos": "세션 내 비디오 연결",
                "DELETE /session/{session_id}": "세션 삭제",
            },
            "기타": {
                "GET /output/{filename}": "결과 다운로드",
                "GET /sessions": "모든 세션 목록",
                "GET /health": "헬스 체크",
            }
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """헬스 체크"""
    ffmpeg_ok = False
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        ffmpeg_ok = result.returncode == 0
    except:
        pass
    
    return {
        "status": "healthy",
        "ffmpeg_available": ffmpeg_ok,
        "upload_dir": UPLOAD_DIR,
        "output_dir": OUTPUT_DIR
    }


# ============================================
# API 엔드포인트 - 업로드
# ============================================
@app.post("/upload/video", response_model=UploadResponse, tags=["Upload"])
async def upload_video(
    video: UploadFile = File(..., description="업로드할 비디오 파일")
):
    """비디오 파일 업로드"""
    try:
        ext = os.path.splitext(video.filename)[1] or ".mp4"
        unique_id = str(uuid.uuid4())[:8]
        filename = f"video_{unique_id}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        with open(filepath, "wb") as f:
            content = await video.read()
            f.write(content)
        
        return UploadResponse(
            success=True,
            filename=filename,
            file_type="video",
            message="비디오 업로드 완료"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


@app.post("/upload/audio", response_model=UploadResponse, tags=["Upload"])
async def upload_audio(
    audio: UploadFile = File(..., description="업로드할 오디오 파일")
):
    """오디오 파일 업로드"""
    try:
        ext = os.path.splitext(audio.filename)[1] or ".mp3"
        unique_id = str(uuid.uuid4())[:8]
        filename = f"audio_{unique_id}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        with open(filepath, "wb") as f:
            content = await audio.read()
            f.write(content)
        
        return UploadResponse(
            success=True,
            filename=filename,
            file_type="audio",
            message="오디오 업로드 완료"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


# ============================================
# API 엔드포인트 - Merge
# ============================================
@app.post("/merge/videos", response_model=MergeResponse, tags=["Merge"])
async def merge_videos(request: MergeVideosRequest):
    """
    비디오 여러개를 순서대로 연결
    
    - **video_files**: 합칠 비디오 파일명 목록 (순서대로)
    - **output_filename**: 출력 파일명 (선택)
    """
    if len(request.video_files) < 2:
        raise HTTPException(status_code=400, detail="최소 2개 이상의 비디오가 필요합니다")
    
    # 파일 존재 확인
    video_paths = []
    for filename in request.video_files:
        # uploads 또는 outputs 폴더에서 찾기
        filepath = os.path.join(UPLOAD_DIR, filename)
        if not os.path.exists(filepath):
            filepath = os.path.join(OUTPUT_DIR, filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {filename}")
        video_paths.append(filepath)
    
    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    output_filename = request.output_filename or f"merged_{timestamp}_{unique_id}.mp4"
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # FFmpeg concat 리스트 파일 생성
    concat_list_path = os.path.join(OUTPUT_DIR, f"concat_{unique_id}.txt")
    
    try:
        with open(concat_list_path, "w") as f:
            for vpath in video_paths:
                f.write(f"file '{os.path.abspath(vpath)}'\n")
        
        # FFmpeg 실행
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path
        ]
        
        print(f"[Merge Videos] {len(video_paths)}개 비디오 합치기 시작")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # 재인코딩으로 재시도
            print("[Merge Videos] copy 실패, 재인코딩 시도...")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg 오류: {result.stderr}")
        
        duration = get_media_duration(output_path)
        
        return MergeResponse(
            success=True,
            output_file=output_filename,
            duration=round(duration, 2),
            message=f"{len(video_paths)}개 비디오 연결 완료 ({duration:.1f}초)"
        )
    
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


@app.post("/merge/audio-video", response_model=MergeResponse, tags=["Merge"])
async def merge_audio_video(request: MergeAudioVideoRequest):
    """
    무음 영상에 오디오 추가
    
    - **video_filename**: 비디오 파일명 (무음 또는 기존 오디오 무시됨)
    - **audio_filename**: 오디오 파일명
    - **output_filename**: 출력 파일명 (선택)
    """
    # 파일 찾기
    video_path = os.path.join(UPLOAD_DIR, request.video_filename)
    if not os.path.exists(video_path):
        video_path = os.path.join(OUTPUT_DIR, request.video_filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"비디오 파일을 찾을 수 없습니다: {request.video_filename}")
    
    audio_path = os.path.join(UPLOAD_DIR, request.audio_filename)
    if not os.path.exists(audio_path):
        audio_path = os.path.join(OUTPUT_DIR, request.audio_filename)
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail=f"오디오 파일을 찾을 수 없습니다: {request.audio_filename}")
    
    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    output_filename = request.output_filename or f"av_merged_{timestamp}_{unique_id}.mp4"
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # FFmpeg: 비디오 + 오디오 합치기 (기존 오디오 무시)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v",        # 첫 번째 입력(비디오)의 비디오 스트림
        "-map", "1:a",        # 두 번째 입력(오디오)의 오디오 스트림
        "-c:v", "copy",       # 비디오 재인코딩 없음
        "-c:a", "aac",        # 오디오 AAC 인코딩
        "-b:a", "192k",
        "-shortest",          # 짧은 쪽에 맞춤
        output_path
    ]
    
    print(f"[Merge Audio-Video] 비디오 + 오디오 합치기")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg 오류: {result.stderr}")
    
    duration = get_media_duration(output_path)
    
    return MergeResponse(
        success=True,
        output_file=output_filename,
        duration=round(duration, 2),
        message=f"비디오 + 오디오 합치기 완료 ({duration:.1f}초)"
    )


@app.post("/merge/audio-video/form", response_model=MergeResponse, tags=["Merge"])
async def merge_audio_video_form(
    video: UploadFile = File(..., description="비디오 파일"),
    audio: UploadFile = File(..., description="오디오 파일"),
    output_filename: Optional[str] = Form(None, description="출력 파일명")
):
    """
    무음 영상에 오디오 추가 (Form-data)
    
    파일을 직접 업로드하여 합치기
    """
    unique_id = str(uuid.uuid4())[:8]
    
    # 비디오 저장
    video_ext = os.path.splitext(video.filename)[1] or ".mp4"
    video_filename = f"temp_video_{unique_id}{video_ext}"
    video_path = os.path.join(UPLOAD_DIR, video_filename)
    with open(video_path, "wb") as f:
        f.write(await video.read())
    
    # 오디오 저장
    audio_ext = os.path.splitext(audio.filename)[1] or ".mp3"
    audio_filename = f"temp_audio_{unique_id}{audio_ext}"
    audio_path = os.path.join(UPLOAD_DIR, audio_filename)
    with open(audio_path, "wb") as f:
        f.write(await audio.read())
    
    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_output = output_filename or f"av_merged_{timestamp}_{unique_id}.mp4"
    if not final_output.endswith(".mp4"):
        final_output += ".mp4"
    output_path = os.path.join(OUTPUT_DIR, final_output)
    
    # FFmpeg 실행
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg 오류: {result.stderr}")
    
    duration = get_media_duration(output_path)
    
    return MergeResponse(
        success=True,
        output_file=final_output,
        duration=round(duration, 2),
        message=f"비디오 + 오디오 합치기 완료 ({duration:.1f}초)"
    )


@app.post("/merge/audio-mix", response_model=MergeResponse, tags=["Merge"])
async def merge_audio_mix(request: AudioMixRequest):
    """
    영상(오디오 포함)에 추가 오디오 믹싱
    
    - **video_filename**: 비디오 파일명 (기존 오디오 포함)
    - **audio_filename**: 추가할 오디오 파일명 (효과음/배경음악)
    - **video_volume**: 비디오 오디오 볼륨 (기본: 1.0)
    - **audio_volume**: 추가 오디오 볼륨 (기본: 0.3)
    - **output_filename**: 출력 파일명 (선택)
    
    예: 립싱크 영상(음성 포함) + 효과음 → 최종 영상
    """
    # 파일 찾기
    video_path = os.path.join(UPLOAD_DIR, request.video_filename)
    if not os.path.exists(video_path):
        video_path = os.path.join(OUTPUT_DIR, request.video_filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"비디오 파일을 찾을 수 없습니다: {request.video_filename}")
    
    audio_path = os.path.join(UPLOAD_DIR, request.audio_filename)
    if not os.path.exists(audio_path):
        audio_path = os.path.join(OUTPUT_DIR, request.audio_filename)
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail=f"오디오 파일을 찾을 수 없습니다: {request.audio_filename}")
    
    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    output_filename = request.output_filename or f"mixed_{timestamp}_{unique_id}.mp4"
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # FFmpeg: 오디오 믹싱 (기존 오디오 + 추가 오디오)
    video_vol = request.video_volume
    audio_vol = request.audio_volume
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex",
        f"[0:a]volume={video_vol}[a0];[1:a]volume={audio_vol}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path
    ]
    
    print(f"[Audio Mix] 오디오 믹싱 (video_vol={video_vol}, audio_vol={audio_vol})")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg 오류: {result.stderr}")
    
    duration = get_media_duration(output_path)
    
    return MergeResponse(
        success=True,
        output_file=output_filename,
        duration=round(duration, 2),
        message=f"오디오 믹싱 완료 ({duration:.1f}초)"
    )


@app.post("/merge/audio-mix/form", response_model=MergeResponse, tags=["Merge"])
async def merge_audio_mix_form(
    video: UploadFile = File(..., description="비디오 파일 (오디오 포함)"),
    audio: UploadFile = File(..., description="추가할 오디오 파일"),
    video_volume: Optional[float] = Form(1.0, description="비디오 오디오 볼륨"),
    audio_volume: Optional[float] = Form(0.3, description="추가 오디오 볼륨"),
    output_filename: Optional[str] = Form(None, description="출력 파일명")
):
    """
    영상(오디오 포함)에 추가 오디오 믹싱 (Form-data)
    
    파일을 직접 업로드하여 믹싱
    """
    unique_id = str(uuid.uuid4())[:8]
    
    # 비디오 저장
    video_ext = os.path.splitext(video.filename)[1] or ".mp4"
    video_filename = f"temp_video_{unique_id}{video_ext}"
    video_path = os.path.join(UPLOAD_DIR, video_filename)
    with open(video_path, "wb") as f:
        f.write(await video.read())
    
    # 오디오 저장
    audio_ext = os.path.splitext(audio.filename)[1] or ".mp3"
    audio_filename = f"temp_audio_{unique_id}{audio_ext}"
    audio_path = os.path.join(UPLOAD_DIR, audio_filename)
    with open(audio_path, "wb") as f:
        f.write(await audio.read())
    
    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_output = output_filename or f"mixed_{timestamp}_{unique_id}.mp4"
    if not final_output.endswith(".mp4"):
        final_output += ".mp4"
    output_path = os.path.join(OUTPUT_DIR, final_output)
    
    # FFmpeg 실행
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex",
        f"[0:a]volume={video_volume}[a0];[1:a]volume={audio_volume}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg 오류: {result.stderr}")
    
    duration = get_media_duration(output_path)
    
    return MergeResponse(
        success=True,
        output_file=final_output,
        duration=round(duration, 2),
        message=f"오디오 믹싱 완료 ({duration:.1f}초)"
    )


# ============================================
# API 엔드포인트 - Output
# ============================================
@app.get("/output/{filename}", tags=["Output"])
async def get_output(filename: str):
    """결과 파일 다운로드"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    # MIME 타입 결정
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".mp4", ".mov", ".avi"]:
        media_type = "video/mp4"
    elif ext in [".mp3", ".wav", ".aac"]:
        media_type = "audio/mpeg"
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(
        filepath,
        media_type=media_type,
        filename=filename
    )


@app.delete("/output/{filename}", tags=["Output"])
async def delete_output(filename: str):
    """결과 파일 삭제"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    os.remove(filepath)
    return {"success": True, "message": f"{filename} 삭제 완료"}


@app.get("/outputs", tags=["Output"])
async def list_outputs():
    """결과 파일 목록"""
    files = []
    for f in Path(OUTPUT_DIR).glob("*"):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
    files.sort(key=lambda x: x["created"], reverse=True)
    return {"files": files, "count": len(files)}


# ============================================
# API 엔드포인트 - 세션 기반 (공유 볼륨)
# ============================================
@app.post("/session/upload", response_model=UploadResponse, tags=["Session"])
async def session_upload(
    session_id: str = Form(..., description="세션 ID"),
    file: UploadFile = File(..., description="업로드할 파일 (비디오/오디오)"),
    filename: Optional[str] = Form(None, description="저장할 파일명 (없으면 원본 파일명 사용)")
):
    """
    세션 폴더에 파일 업로드
    
    다른 서비스에서도 이 세션 폴더에 접근 가능
    """
    try:
        session_dir = get_session_dir(session_id)
        
        # 파일명 결정
        save_filename = filename or file.filename
        filepath = os.path.join(session_dir, save_filename)
        
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # 파일 타입 추론
        ext = os.path.splitext(save_filename)[1].lower()
        if ext in [".mp4", ".mov", ".avi", ".webm"]:
            file_type = "video"
        elif ext in [".mp3", ".wav", ".aac", ".m4a"]:
            file_type = "audio"
        else:
            file_type = "unknown"
        
        return UploadResponse(
            success=True,
            filename=save_filename,
            file_type=file_type,
            message=f"세션 '{session_id}'에 업로드 완료",
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


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


@app.get("/session/{session_id}/file/{filename}", tags=["Session"])
async def get_session_file(session_id: str, filename: str):
    """세션 폴더 내 파일 다운로드"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    filepath = os.path.join(session_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {session_id}/{filename}")
    
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".mp4", ".mov", ".avi"]:
        media_type = "video/mp4"
    elif ext in [".mp3"]:
        media_type = "audio/mpeg"
    elif ext in [".wav"]:
        media_type = "audio/wav"
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(filepath, media_type=media_type, filename=filename)


@app.post("/session/merge/audio-video", response_model=MergeResponse, tags=["Session"])
async def session_merge_audio_video(request: SessionAudioVideoRequest):
    """
    세션 폴더 내 파일로 비디오 + 오디오 합치기
    
    - **session_id**: 세션 ID
    - **video_filename**: 세션 폴더 내 비디오 파일명
    - **audio_filename**: 세션 폴더 내 오디오 파일명
    - **output_filename**: 출력 파일명 (세션 폴더에 저장됨)
    """
    try:
        video_path = find_file_in_session(request.session_id, request.video_filename)
        audio_path = find_file_in_session(request.session_id, request.audio_filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    session_dir = get_session_dir(request.session_id)
    output_filename = request.output_filename or "merged.mp4"
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    output_path = os.path.join(session_dir, output_filename)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    
    print(f"[Session Merge] {request.session_id}: 비디오 + 오디오 합치기")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg 오류: {result.stderr}")
    
    duration = get_media_duration(output_path)
    
    return MergeResponse(
        success=True,
        output_file=output_filename,
        duration=round(duration, 2),
        message=f"비디오 + 오디오 합치기 완료 ({duration:.1f}초)",
        session_id=request.session_id
    )


@app.post("/session/merge/audio-mix", response_model=MergeResponse, tags=["Session"])
async def session_merge_audio_mix(request: SessionAudioMixRequest):
    """
    세션 폴더 내 영상(오디오 포함)에 추가 오디오 믹싱
    
    - **session_id**: 세션 ID
    - **video_filename**: 비디오 파일명 (기존 오디오 포함, 예: 립싱크 영상)
    - **audio_filename**: 추가할 오디오 파일명 (예: 효과음)
    - **video_volume**: 비디오 오디오 볼륨 (기본: 1.0)
    - **audio_volume**: 추가 오디오 볼륨 (기본: 0.3)
    - **output_filename**: 출력 파일명 (세션 폴더에 저장됨)
    """
    try:
        video_path = find_file_in_session(request.session_id, request.video_filename)
        audio_path = find_file_in_session(request.session_id, request.audio_filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    session_dir = get_session_dir(request.session_id)
    output_filename = request.output_filename or "final.mp4"
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    output_path = os.path.join(session_dir, output_filename)
    
    video_vol = request.video_volume
    audio_vol = request.audio_volume
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex",
        f"[0:a]volume={video_vol}[a0];[1:a]volume={audio_vol}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path
    ]
    
    print(f"[Session Audio Mix] {request.session_id}: 오디오 믹싱 (video_vol={video_vol}, audio_vol={audio_vol})")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg 오류: {result.stderr}")
    
    duration = get_media_duration(output_path)
    
    return MergeResponse(
        success=True,
        output_file=output_filename,
        duration=round(duration, 2),
        message=f"오디오 믹싱 완료 ({duration:.1f}초)",
        session_id=request.session_id
    )


@app.post("/session/merge/videos", response_model=MergeResponse, tags=["Session"])
async def session_merge_videos(request: SessionMergeVideosRequest):
    """
    세션 폴더 내 비디오 여러개 순서대로 연결
    
    - **session_id**: 세션 ID
    - **video_files**: 합칠 비디오 파일명 목록 (순서대로)
    - **output_filename**: 출력 파일명 (세션 폴더에 저장됨)
    """
    if len(request.video_files) < 2:
        raise HTTPException(status_code=400, detail="최소 2개 이상의 비디오가 필요합니다")
    
    # 파일 존재 확인
    video_paths = []
    for filename in request.video_files:
        try:
            filepath = find_file_in_session(request.session_id, filename)
            video_paths.append(filepath)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
    
    session_dir = get_session_dir(request.session_id)
    output_filename = request.output_filename or "merged.mp4"
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    output_path = os.path.join(session_dir, output_filename)
    
    # FFmpeg concat 리스트
    unique_id = str(uuid.uuid4())[:8]
    concat_list_path = os.path.join(session_dir, f"concat_{unique_id}.txt")
    
    try:
        with open(concat_list_path, "w") as f:
            for vpath in video_paths:
                f.write(f"file '{os.path.abspath(vpath)}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path
        ]
        
        print(f"[Session Merge Videos] {request.session_id}: {len(video_paths)}개 비디오 연결")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # 재인코딩 시도
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg 오류: {result.stderr}")
        
        duration = get_media_duration(output_path)
        
        return MergeResponse(
            success=True,
            output_file=output_filename,
            duration=round(duration, 2),
            message=f"{len(video_paths)}개 비디오 연결 완료 ({duration:.1f}초)",
            session_id=request.session_id
        )
    
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


@app.delete("/session/{session_id}", tags=["Session"])
async def delete_session(session_id: str):
    """세션 폴더 전체 삭제"""
    import shutil
    
    session_dir = os.path.join(SHARED_DIR, session_id)
    
    if not os.path.exists(session_dir):
        raise HTTPException(status_code=404, detail=f"세션을 찾을 수 없습니다: {session_id}")
    
    shutil.rmtree(session_dir)
    return {"success": True, "message": f"세션 '{session_id}' 삭제 완료"}


@app.get("/sessions", tags=["Session"])
async def list_sessions():
    """모든 세션 목록 조회"""
    sessions = []
    for d in Path(SHARED_DIR).iterdir():
        if d.is_dir():
            file_count = len(list(d.glob("*")))
            sessions.append({
                "session_id": d.name,
                "file_count": file_count,
                "created": datetime.fromtimestamp(d.stat().st_ctime).isoformat()
            })
    sessions.sort(key=lambda x: x["created"], reverse=True)
    return {"sessions": sessions, "count": len(sessions)}


# ============================================
# 메인 실행
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

