"""
LatentSync 립싱크 API
ComfyUI를 통한 비디오 + 오디오 → 립싱크 영상 생성 API
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import uuid
import time
import asyncio
from datetime import datetime
from pathlib import Path

from comfyui_client import ComfyUIClient

# ============================================
# FastAPI 앱 초기화
# ============================================
app = FastAPI(
    title="LatentSync 립싱크 API",
    description="ComfyUI 기반 비디오 + 오디오 → 립싱크 영상 생성 API (LatentSync 1.6)",
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
# 환경변수 및 설정
# ============================================
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8000")
WORKFLOW_PATH = os.getenv("WORKFLOW_PATH", "workflows/latentsync1.6.json")

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
WORKFLOW_DIR = "workflows"
SHARED_DIR = "shared"  # 공유 볼륨 (다른 서비스와 공유)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WORKFLOW_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)

# ComfyUI 클라이언트
client = ComfyUIClient(COMFYUI_URL)

# 파일 자동 삭제 설정
FILE_MAX_AGE_HOURS = 2


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
        await asyncio.sleep(1800)  # 30분
        cleanup_old_files(OUTPUT_DIR)
        cleanup_old_files(UPLOAD_DIR)


# ============================================
# Pydantic 모델
# ============================================
class LipSyncRequest(BaseModel):
    """립싱크 생성 요청 (JSON Body용)"""
    video_filename: str = Field(..., description="입력 비디오 파일명 (업로드된)")
    audio_filename: str = Field(..., description="입력 오디오 파일명 (업로드된)")
    seed: Optional[int] = Field(None, description="랜덤 시드 (없으면 자동 생성)")
    lips_expression: Optional[float] = Field(1.5, description="입술 표현 강도 (기본: 1.5)")
    inference_steps: Optional[int] = Field(20, description="추론 스텝 (기본: 20)")
    fps: Optional[int] = Field(25, description="프레임레이트 (기본: 25)")


class SessionLipSyncRequest(BaseModel):
    """세션 기반 립싱크 생성 요청"""
    session_id: str = Field(..., description="세션 ID (공유 폴더 내)")
    video_filename: str = Field(..., description="세션 폴더 내 비디오 파일명")
    audio_filename: str = Field(..., description="세션 폴더 내 오디오 파일명")
    output_filename: Optional[str] = Field("lipsync.mp4", description="출력 파일명 (세션 폴더에 저장)")
    seed: Optional[int] = Field(None, description="랜덤 시드")
    lips_expression: Optional[float] = Field(1.5, description="입술 표현 강도")
    inference_steps: Optional[int] = Field(20, description="추론 스텝")
    fps: Optional[int] = Field(25, description="프레임레이트")


class LipSyncResponse(BaseModel):
    """립싱크 생성 응답"""
    success: bool
    output_file: str
    message: str
    processing_time: float
    session_id: Optional[str] = Field(None, description="세션 ID (세션 기반 요청시)")


class UploadResponse(BaseModel):
    """업로드 응답"""
    success: bool
    filename: str
    file_type: str
    message: str


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    status: str
    comfyui_url: str
    comfyui_connected: bool
    workflow_exists: bool


# ============================================
# 이벤트 핸들러
# ============================================
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    print(f"LatentSync 립싱크 API 시작...")
    print(f"ComfyUI URL: {COMFYUI_URL}")
    print(f"Workflow Path: {WORKFLOW_PATH}")
    
    # 오래된 파일 정리
    cleanup_old_files(OUTPUT_DIR)
    cleanup_old_files(UPLOAD_DIR)
    
    # 백그라운드 정리 태스크
    asyncio.create_task(periodic_cleanup())
    print(f"[Cleanup] 자동 파일 정리 활성화 ({FILE_MAX_AGE_HOURS}시간 이상 파일 삭제)")
    
    # 워크플로우 파일 확인
    if os.path.exists(WORKFLOW_PATH):
        print(f"워크플로우 파일 확인됨: {WORKFLOW_PATH}")
    else:
        print(f"경고: 워크플로우 파일이 없습니다: {WORKFLOW_PATH}")


# ============================================
# API 엔드포인트
# ============================================
@app.get("/", tags=["Root"])
async def root():
    """API 루트"""
    return {
        "message": "LatentSync 립싱크 API",
        "version": "1.0.0",
        "description": "비디오와 오디오를 입력받아 립싱크 영상을 생성합니다 (LatentSync 1.6)",
        "endpoints": {
            "POST /upload/video": "비디오 업로드",
            "POST /upload/audio": "오디오 업로드",
            "POST /generate": "립싱크 생성 (Form-data)",
            "POST /generate/json": "립싱크 생성 (JSON)",
            "GET /output/{filename}": "결과 영상 다운로드",
            "GET /health": "헬스 체크"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """헬스 체크"""
    comfyui_ok = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.get(f"{COMFYUI_URL}/system_stats")
            comfyui_ok = response.status_code == 200
    except:
        pass
    
    return HealthResponse(
        status="healthy",
        comfyui_url=COMFYUI_URL,
        comfyui_connected=comfyui_ok,
        workflow_exists=os.path.exists(WORKFLOW_PATH)
    )


@app.post("/upload/video", response_model=UploadResponse, tags=["Upload"])
async def upload_video(
    video: UploadFile = File(..., description="업로드할 비디오 파일 (mp4)")
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
        
        # ComfyUI에도 업로드
        try:
            await client.upload_file(filepath, filename, file_type="video")
        except Exception as e:
            print(f"ComfyUI 업로드 실패 (나중에 재시도): {e}")
        
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
    audio: UploadFile = File(..., description="업로드할 오디오 파일 (mp3/wav)")
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
        
        # ComfyUI에도 업로드
        try:
            await client.upload_file(filepath, filename, file_type="audio")
        except Exception as e:
            print(f"ComfyUI 업로드 실패 (나중에 재시도): {e}")
        
        return UploadResponse(
            success=True,
            filename=filename,
            file_type="audio",
            message="오디오 업로드 완료"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


@app.post("/generate", response_model=LipSyncResponse, tags=["LipSync"])
async def generate_lipsync_form(
    video: UploadFile = File(..., description="입력 비디오"),
    audio: UploadFile = File(..., description="입력 오디오"),
    seed: Optional[int] = Form(None, description="랜덤 시드"),
    lips_expression: Optional[float] = Form(1.5, description="입술 표현 강도"),
    inference_steps: Optional[int] = Form(20, description="추론 스텝"),
    fps: Optional[int] = Form(25, description="프레임레이트"),
):
    """
    립싱크 영상 생성 (Form-data)
    
    - **video**: 입력 비디오 파일 (mp4)
    - **audio**: 입력 오디오 파일 (mp3/wav)
    - **seed**: 랜덤 시드 (없으면 자동 생성)
    - **lips_expression**: 입술 표현 강도 (기본: 1.5, 높을수록 강조)
    - **inference_steps**: 추론 스텝 (기본: 20, 높을수록 품질↑)
    - **fps**: 프레임레이트 (기본: 25)
    """
    start_time = time.time()
    
    try:
        # 워크플로우 로드
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        unique_id = str(uuid.uuid4())[:8]
        
        # 비디오 저장 및 업로드
        video_ext = os.path.splitext(video.filename)[1] or ".mp4"
        video_filename = f"lipsync_video_{unique_id}{video_ext}"
        video_path = os.path.join(UPLOAD_DIR, video_filename)
        with open(video_path, "wb") as f:
            f.write(await video.read())
        await client.upload_file(video_path, video_filename, file_type="video")
        
        # 오디오 저장 및 업로드
        audio_ext = os.path.splitext(audio.filename)[1] or ".mp3"
        audio_filename = f"lipsync_audio_{unique_id}{audio_ext}"
        audio_path = os.path.join(UPLOAD_DIR, audio_filename)
        with open(audio_path, "wb") as f:
            f.write(await audio.read())
        await client.upload_file(audio_path, audio_filename, file_type="audio")
        
        # 워크플로우 업데이트
        workflow = client.update_lipsync_workflow(
            workflow,
            video_filename=video_filename,
            audio_filename=audio_filename,
            seed=seed,
            lips_expression=lips_expression,
            inference_steps=inference_steps,
            fps=fps
        )
        
        # 실행
        result = await client.execute_workflow(workflow, timeout=1800)
        
        # 결과 비디오 가져오기
        outputs = result.get("outputs", {})
        output_videos = []
        
        for node_id, node_output in outputs.items():
            if isinstance(node_output, dict):
                if "gifs" in node_output:
                    for vid in node_output["gifs"]:
                        output_videos.append(vid)
        
        if not output_videos:
            raise HTTPException(status_code=500, detail="출력 비디오가 없습니다")
        
        # 첫 번째 출력 비디오 저장
        vid_info = output_videos[0]
        vid_bytes = await client.get_video(
            vid_info["filename"],
            vid_info.get("subfolder", ""),
            vid_info.get("type", "output")
        )
        
        # 로컬에 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"lipsync_{timestamp}_{unique_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(vid_bytes)
        
        processing_time = time.time() - start_time
        
        return LipSyncResponse(
            success=True,
            output_file=output_filename,
            message="립싱크 영상 생성 완료",
            processing_time=round(processing_time, 2)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] 립싱크 생성 실패:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"립싱크 생성 실패: {str(e)}")


@app.post("/generate/json", response_model=LipSyncResponse, tags=["LipSync"])
async def generate_lipsync_json(request: LipSyncRequest):
    """
    립싱크 영상 생성 (JSON) - 미리 업로드된 파일 사용
    """
    start_time = time.time()
    
    try:
        # 워크플로우 로드
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        # 워크플로우 업데이트
        workflow = client.update_lipsync_workflow(
            workflow,
            video_filename=request.video_filename,
            audio_filename=request.audio_filename,
            seed=request.seed,
            lips_expression=request.lips_expression,
            inference_steps=request.inference_steps,
            fps=request.fps
        )
        
        # 실행
        result = await client.execute_workflow(workflow, timeout=1800)
        
        # 결과 처리
        outputs = result.get("outputs", {})
        output_videos = []
        
        for node_id, node_output in outputs.items():
            if isinstance(node_output, dict) and "gifs" in node_output:
                for vid in node_output["gifs"]:
                    output_videos.append(vid)
        
        if not output_videos:
            raise HTTPException(status_code=500, detail="출력 비디오가 없습니다")
        
        # 비디오 저장
        vid_info = output_videos[0]
        vid_bytes = await client.get_video(
            vid_info["filename"],
            vid_info.get("subfolder", ""),
            vid_info.get("type", "output")
        )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        output_filename = f"lipsync_{timestamp}_{unique_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(vid_bytes)
        
        processing_time = time.time() - start_time
        
        return LipSyncResponse(
            success=True,
            output_file=output_filename,
            message="립싱크 영상 생성 완료",
            processing_time=round(processing_time, 2)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"립싱크 생성 실패: {str(e)}")


@app.get("/output/{filename}", tags=["Output"])
async def get_output(filename: str):
    """결과 영상 다운로드"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    return FileResponse(
        filepath,
        media_type="video/mp4",
        filename=filename
    )


@app.delete("/output/{filename}", tags=["Output"])
async def delete_output(filename: str):
    """결과 영상 삭제"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    os.remove(filepath)
    return {"success": True, "message": f"{filename} 삭제 완료"}


@app.get("/outputs", tags=["Output"])
async def list_outputs():
    """결과 영상 목록"""
    files = []
    for f in Path(OUTPUT_DIR).glob("*.mp4"):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
    files.sort(key=lambda x: x["created"], reverse=True)
    return {"files": files, "count": len(files)}


# ============================================
# 세션 기반 엔드포인트 (공유 볼륨)
# ============================================
def get_session_dir(session_id: str) -> str:
    """세션 디렉토리 경로 반환 (없으면 생성)"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


@app.post("/session/generate", response_model=LipSyncResponse, tags=["Session"])
async def session_generate_lipsync(request: SessionLipSyncRequest):
    """
    세션 기반 립싱크 생성
    
    - **session_id**: 세션 ID (공유 폴더 내 하위 폴더)
    - **video_filename**: 세션 폴더 내 비디오 파일명
    - **audio_filename**: 세션 폴더 내 오디오 파일명
    - **output_filename**: 출력 파일명 (세션 폴더에 저장됨)
    
    다른 서비스에서 저장한 파일을 사용하고, 결과도 세션 폴더에 저장됩니다.
    """
    start_time = time.time()
    
    try:
        session_dir = get_session_dir(request.session_id)
        
        # 세션 폴더에서 파일 찾기
        video_path = os.path.join(session_dir, request.video_filename)
        audio_path = os.path.join(session_dir, request.audio_filename)
        
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"비디오 파일을 찾을 수 없습니다: {request.video_filename}")
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail=f"오디오 파일을 찾을 수 없습니다: {request.audio_filename}")
        
        # 워크플로우 로드
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        unique_id = str(uuid.uuid4())[:8]
        
        # ComfyUI에 업로드 (세션 폴더에서)
        comfy_video_name = f"session_{request.session_id}_{request.video_filename}"
        comfy_audio_name = f"session_{request.session_id}_{request.audio_filename}"
        
        await client.upload_file(video_path, comfy_video_name, file_type="video")
        await client.upload_file(audio_path, comfy_audio_name, file_type="audio")
        
        # 워크플로우 업데이트
        workflow = client.update_lipsync_workflow(
            workflow,
            video_filename=comfy_video_name,
            audio_filename=comfy_audio_name,
            seed=request.seed,
            lips_expression=request.lips_expression,
            inference_steps=request.inference_steps,
            fps=request.fps
        )
        
        # 실행
        result = await client.execute_workflow(workflow, timeout=1800)
        
        # 결과 비디오 가져오기
        outputs = result.get("outputs", {})
        output_videos = []
        
        for node_id, node_output in outputs.items():
            if isinstance(node_output, dict) and "gifs" in node_output:
                for vid in node_output["gifs"]:
                    output_videos.append(vid)
        
        if not output_videos:
            raise HTTPException(status_code=500, detail="출력 비디오가 없습니다")
        
        # 비디오 저장 (세션 폴더에)
        vid_info = output_videos[0]
        vid_bytes = await client.get_video(
            vid_info["filename"],
            vid_info.get("subfolder", ""),
            vid_info.get("type", "output")
        )
        
        output_filename = request.output_filename or "lipsync.mp4"
        if not output_filename.endswith(".mp4"):
            output_filename += ".mp4"
        output_path = os.path.join(session_dir, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(vid_bytes)
        
        processing_time = time.time() - start_time
        
        return LipSyncResponse(
            success=True,
            output_file=output_filename,
            message=f"세션 '{request.session_id}'에 립싱크 영상 저장 완료",
            processing_time=round(processing_time, 2),
            session_id=request.session_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] 세션 립싱크 생성 실패:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"립싱크 생성 실패: {str(e)}")


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


# ============================================
# 메인 실행
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2100)

