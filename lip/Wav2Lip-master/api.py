from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
import subprocess
import shutil
from datetime import datetime

# FastAPI 앱 초기화
app = FastAPI(title="Wav2Lip API", version="1.0.0")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 디렉토리 설정
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "results"
TEMP_DIR = "temp"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 기본 체크포인트 경로
DEFAULT_CHECKPOINT = "checkpoints/Wav2Lip-SD-GAN.pt"


class LipsyncResponse(BaseModel):
    """Lipsync 응답 모델"""
    success: bool
    video_file: str
    message: str


class MergeResponse(BaseModel):
    """영상 합치기 응답 모델"""
    success: bool
    merged_file: str
    message: str


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    print("Wav2Lip API 서버 시작...")
    
    # 체크포인트 파일 확인
    if os.path.exists(DEFAULT_CHECKPOINT):
        print(f"모델 체크포인트 확인됨: {DEFAULT_CHECKPOINT}")
    else:
        print(f"경고: 모델 체크포인트를 찾을 수 없습니다: {DEFAULT_CHECKPOINT}")
    
    print("Wav2Lip API 준비 완료!")


@app.get("/")
async def root():
    """API 루트 엔드포인트"""
    return {
        "message": "Wav2Lip API",
        "version": "1.0.0",
        "endpoints": {
            "POST /lipsync": "영상 + 음성 → 입모양 싱크 영상 생성",
            "GET /video/{filename}": "생성된 영상 다운로드",
            "POST /merge": "여러 영상 합치기",
            "GET /health": "헬스 체크"
        }
    }


@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    checkpoint_exists = os.path.exists(DEFAULT_CHECKPOINT)
    return {
        "status": "healthy",
        "checkpoint_loaded": checkpoint_exists,
        "checkpoint_path": DEFAULT_CHECKPOINT
    }


@app.post("/lipsync", response_model=LipsyncResponse)
async def create_lipsync(
    face_video: UploadFile = File(..., description="얼굴이 있는 영상 파일"),
    audio_file: UploadFile = File(..., description="음성 파일 (.wav, .mp3)"),
    checkpoint: Optional[str] = Form(DEFAULT_CHECKPOINT, description="모델 체크포인트 경로")
):
    """
    영상과 음성을 받아 입모양 싱크 영상 생성
    
    - **face_video**: 얼굴이 있는 영상 파일 (mp4, avi 등)
    - **audio_file**: 음성 파일 (wav, mp3)
    - **checkpoint**: 모델 체크포인트 (기본값: Wav2Lip-SD-GAN.pt)
    """
    try:
        # 고유 ID 생성
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 업로드 파일 저장
        face_ext = os.path.splitext(face_video.filename)[1] or ".mp4"
        audio_ext = os.path.splitext(audio_file.filename)[1] or ".wav"
        
        face_path = os.path.join(UPLOAD_DIR, f"face_{unique_id}{face_ext}")
        audio_path = os.path.join(UPLOAD_DIR, f"audio_{unique_id}{audio_ext}")
        output_filename = f"lipsync_{timestamp}_{unique_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # 파일 저장
        with open(face_path, "wb") as f:
            content = await face_video.read()
            f.write(content)
        
        with open(audio_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
        
        # inference.py 실행
        cmd = [
            "python", "inference.py",
            "--checkpoint_path", checkpoint,
            "--face", face_path,
            "--audio", audio_path,
            "--outfile", output_path
        ]
        
        print(f"실행 명령: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10분 타임아웃
        )
        
        # 업로드 파일 정리
        if os.path.exists(face_path):
            os.remove(face_path)
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        # 결과 확인
        if result.returncode != 0:
            print(f"에러 출력: {result.stderr}")
            raise HTTPException(
                status_code=500, 
                detail=f"Lipsync 생성 실패: {result.stderr[:500]}"
            )
        
        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=500, 
                detail="출력 파일이 생성되지 않았습니다"
            )
        
        return LipsyncResponse(
            success=True,
            video_file=output_filename,
            message="Lipsync 영상 생성 완료"
        )
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="처리 시간 초과 (10분)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lipsync 생성 실패: {str(e)}")


@app.post("/lipsync/local", response_model=LipsyncResponse)
async def create_lipsync_local(
    face_path: str = Form(..., description="서버 내 얼굴 영상 경로"),
    audio_path: str = Form(..., description="서버 내 음성 파일 경로"),
    checkpoint: Optional[str] = Form(DEFAULT_CHECKPOINT, description="모델 체크포인트 경로")
):
    """
    서버 내 파일 경로로 입모양 싱크 영상 생성 (테스트용)
    
    - **face_path**: 서버 내 얼굴 영상 파일 경로
    - **audio_path**: 서버 내 음성 파일 경로
    """
    try:
        # 파일 존재 확인
        if not os.path.exists(face_path):
            raise HTTPException(status_code=404, detail=f"얼굴 영상 파일을 찾을 수 없습니다: {face_path}")
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail=f"음성 파일을 찾을 수 없습니다: {audio_path}")
        
        # 고유 ID 생성
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"lipsync_{timestamp}_{unique_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # inference.py 실행
        cmd = [
            "python", "inference.py",
            "--checkpoint_path", checkpoint,
            "--face", face_path,
            "--audio", audio_path,
            "--outfile", output_path
        ]
        
        print(f"실행 명령: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode != 0:
            print(f"에러 출력: {result.stderr}")
            raise HTTPException(
                status_code=500, 
                detail=f"Lipsync 생성 실패: {result.stderr[:500]}"
            )
        
        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=500, 
                detail="출력 파일이 생성되지 않았습니다"
            )
        
        return LipsyncResponse(
            success=True,
            video_file=output_filename,
            message="Lipsync 영상 생성 완료"
        )
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="처리 시간 초과 (10분)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lipsync 생성 실패: {str(e)}")


@app.post("/merge", response_model=MergeResponse)
async def merge_videos(
    video_files: List[UploadFile] = File(..., description="합칠 영상 파일들")
):
    """
    여러 영상을 하나로 합치기
    
    - **video_files**: 합칠 영상 파일들 (순서대로 합쳐짐)
    """
    try:
        if len(video_files) < 2:
            raise HTTPException(status_code=400, detail="최소 2개 이상의 영상이 필요합니다")
        
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 임시 파일 저장
        temp_files = []
        for i, video in enumerate(video_files):
            ext = os.path.splitext(video.filename)[1] or ".mp4"
            temp_path = os.path.join(TEMP_DIR, f"merge_{unique_id}_{i}{ext}")
            with open(temp_path, "wb") as f:
                content = await video.read()
                f.write(content)
            temp_files.append(temp_path)
        
        # ffmpeg용 파일 리스트 생성
        list_file = os.path.join(TEMP_DIR, f"merge_list_{unique_id}.txt")
        with open(list_file, "w") as f:
            for temp_file in temp_files:
                f.write(f"file '{os.path.abspath(temp_file)}'\n")
        
        # 출력 파일
        output_filename = f"merged_{timestamp}_{unique_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # ffmpeg로 영상 합치기
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # 임시 파일 정리
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        if os.path.exists(list_file):
            os.remove(list_file)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=500, 
                detail=f"영상 합치기 실패: {result.stderr[:500]}"
            )
        
        return MergeResponse(
            success=True,
            merged_file=output_filename,
            message=f"{len(video_files)}개 영상 합치기 완료"
        )
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="처리 시간 초과")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"영상 합치기 실패: {str(e)}")


@app.get("/video/{filename}")
async def get_video(filename: str):
    """생성된 영상 파일 다운로드"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    return FileResponse(
        filepath,
        media_type="video/mp4",
        filename=filename
    )


@app.delete("/video/{filename}")
async def delete_video(filename: str):
    """생성된 영상 파일 삭제"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    os.remove(filepath)
    return {"success": True, "message": f"{filename} 삭제 완료"}


@app.get("/videos")
async def list_videos():
    """생성된 영상 목록 조회"""
    videos = []
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith(('.mp4', '.avi', '.mov')):
            filepath = os.path.join(OUTPUT_DIR, filename)
            videos.append({
                "filename": filename,
                "size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat()
            })
    return {"videos": videos, "count": len(videos)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2000)

