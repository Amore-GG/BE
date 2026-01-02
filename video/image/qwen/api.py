"""
Qwen Image Edit API
ComfyUI를 통한 이미지 편집 API (z_image와 동일한 구조)
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
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
    title="Qwen Image Edit API",
    description="ComfyUI 기반 이미지 편집 API",
    version="2.0.0"
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
WORKFLOW_PATH = os.getenv("WORKFLOW_PATH", "workflows/image_qwen_image_edit_2509.json")

OUTPUT_DIR = "outputs"
UPLOAD_DIR = "uploads"
SHARED_DIR = "shared"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
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


def get_session_dir(session_id: str) -> str:
    """세션 디렉토리 경로 반환 (없으면 생성)"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


# ============================================
# Pydantic 모델
# ============================================
class ImageEditRequest(BaseModel):
    """이미지 편집 요청 (JSON)"""
    prompt: str = Field(..., description="편집 프롬프트")
    image1_filename: str = Field(..., description="첫 번째 이미지 파일명")
    image2_filename: Optional[str] = Field(None, description="두 번째 이미지 파일명 (선택)")


class SessionImageEditRequest(BaseModel):
    """세션 기반 이미지 편집 요청"""
    session_id: str = Field(..., description="세션 ID")
    prompt: str = Field(..., description="편집 프롬프트")
    image1_filename: str = Field(..., description="세션 내 첫 번째 이미지 파일명")
    image2_filename: Optional[str] = Field(None, description="세션 내 두 번째 이미지 파일명 (선택)")
    output_filename: Optional[str] = Field("edited.png", description="출력 파일명")


class ImageEditResponse(BaseModel):
    """이미지 편집 응답"""
    success: bool
    output_file: str
    message: str
    processing_time: float
    session_id: Optional[str] = None


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
    print(f"Qwen Image Edit API 시작...")
    print(f"ComfyUI URL: {COMFYUI_URL}")
    print(f"Workflow Path: {WORKFLOW_PATH}")
    
    cleanup_old_files(OUTPUT_DIR)
    cleanup_old_files(UPLOAD_DIR)
    
    asyncio.create_task(periodic_cleanup())
    print(f"[Cleanup] 자동 파일 정리 활성화 ({FILE_MAX_AGE_HOURS}시간 이상 파일 삭제)")
    
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
        "message": "Qwen Image Edit API",
        "version": "2.0.0",
        "endpoints": {
            "POST /edit": "이미지 편집 (Form-data, 이미지 직접 업로드)",
            "POST /edit/json": "이미지 편집 (JSON, 미리 업로드된 이미지)",
            "POST /session/edit": "세션 기반 이미지 편집",
            "GET /session/{session_id}/files": "세션 파일 목록",
            "GET /session/{session_id}/file/{filename}": "세션 파일 다운로드",
            "GET /output/{filename}": "결과 이미지 다운로드",
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


# ============================================
# 일반 편집 엔드포인트
# ============================================
@app.post("/edit", response_model=ImageEditResponse, tags=["Edit"])
async def edit_image_form(
    prompt: str = Form(..., description="편집 프롬프트"),
    image1: UploadFile = File(..., description="첫 번째 이미지"),
    image2: Optional[UploadFile] = File(None, description="두 번째 이미지 (선택)"),
):
    """
    이미지 편집 (Form-data) - 이미지 직접 업로드
    """
    start_time = time.time()
    
    try:
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        unique_id = str(uuid.uuid4())[:8]
        
        # Image 1 저장 및 업로드
        ext1 = os.path.splitext(image1.filename)[1] or ".png"
        image1_filename = f"edit_{unique_id}_1{ext1}"
        image1_path = os.path.join(UPLOAD_DIR, image1_filename)
        with open(image1_path, "wb") as f:
            f.write(await image1.read())
        await client.upload_image(image1_path, image1_filename)
        
        # Image 2 저장 및 업로드 (선택)
        image2_filename = None
        if image2 and image2.filename:
            ext2 = os.path.splitext(image2.filename)[1] or ".png"
            image2_filename = f"edit_{unique_id}_2{ext2}"
            image2_path = os.path.join(UPLOAD_DIR, image2_filename)
            with open(image2_path, "wb") as f:
                f.write(await image2.read())
            await client.upload_image(image2_path, image2_filename)
        
        # 워크플로우 업데이트 및 실행
        workflow = client.update_workflow_images(workflow, image1_filename, image2_filename)
        workflow = client.update_workflow_prompt(workflow, prompt)
        workflow = client.randomize_seed(workflow)
        
        result = await client.execute_workflow(workflow, timeout=600)
        
        # 결과 이미지 처리
        outputs = result.get("outputs", {})
        output_images = []
        for node_id, node_output in outputs.items():
            if isinstance(node_output, dict) and "images" in node_output:
                for img in node_output["images"]:
                    output_images.append(img)
        
        if not output_images:
            raise HTTPException(status_code=500, detail="출력 이미지가 없습니다")
        
        img_info = output_images[0]
        img_bytes = await client.get_image(
            img_info["filename"],
            img_info.get("subfolder", ""),
            img_info.get("type", "output")
        )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"qwen_{timestamp}_{unique_id}.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageEditResponse(
            success=True,
            output_file=output_filename,
            message="이미지 편집 완료",
            processing_time=round(processing_time, 2)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] /edit 실패:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"이미지 편집 실패: {str(e)}")


@app.post("/edit/json", response_model=ImageEditResponse, tags=["Edit"])
async def edit_image_json(request: ImageEditRequest):
    """
    이미지 편집 (JSON) - 미리 업로드된 이미지 사용
    """
    start_time = time.time()
    
    try:
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        workflow = client.update_workflow_images(
            workflow,
            request.image1_filename,
            request.image2_filename
        )
        workflow = client.update_workflow_prompt(workflow, request.prompt)
        workflow = client.randomize_seed(workflow)
        
        result = await client.execute_workflow(workflow, timeout=600)
        
        outputs = result.get("outputs", {})
        output_images = []
        for node_id, node_output in outputs.items():
            if isinstance(node_output, dict) and "images" in node_output:
                for img in node_output["images"]:
                    output_images.append(img)
        
        if not output_images:
            raise HTTPException(status_code=500, detail="출력 이미지가 없습니다")
        
        img_info = output_images[0]
        img_bytes = await client.get_image(
            img_info["filename"],
            img_info.get("subfolder", ""),
            img_info.get("type", "output")
        )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        output_filename = f"qwen_{timestamp}_{unique_id}.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageEditResponse(
            success=True,
            output_file=output_filename,
            message="이미지 편집 완료",
            processing_time=round(processing_time, 2)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] /edit/json 실패:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"이미지 편집 실패: {str(e)}")


# ============================================
# 세션 기반 엔드포인트
# ============================================
@app.post("/session/edit", response_model=ImageEditResponse, tags=["Session"])
async def session_edit_image(request: SessionImageEditRequest):
    """
    세션 기반 이미지 편집
    
    - 세션 폴더 내 이미지를 사용
    - 결과도 세션 폴더에 저장
    """
    start_time = time.time()
    
    try:
        session_dir = get_session_dir(request.session_id)
        
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        # 세션 폴더에서 이미지 확인 및 ComfyUI 업로드
        image1_path = os.path.join(session_dir, request.image1_filename)
        if not os.path.exists(image1_path):
            raise HTTPException(status_code=404, detail=f"이미지를 찾을 수 없습니다: {request.image1_filename}")
        await client.upload_image(image1_path, request.image1_filename)
        
        image2_filename = None
        if request.image2_filename:
            image2_path = os.path.join(session_dir, request.image2_filename)
            if not os.path.exists(image2_path):
                raise HTTPException(status_code=404, detail=f"이미지를 찾을 수 없습니다: {request.image2_filename}")
            await client.upload_image(image2_path, request.image2_filename)
            image2_filename = request.image2_filename
        
        # 워크플로우 업데이트 및 실행
        workflow = client.update_workflow_images(workflow, request.image1_filename, image2_filename)
        workflow = client.update_workflow_prompt(workflow, request.prompt)
        workflow = client.randomize_seed(workflow)
        
        result = await client.execute_workflow(workflow, timeout=600)
        
        # 결과 이미지 처리
        outputs = result.get("outputs", {})
        output_images = []
        for node_id, node_output in outputs.items():
            if isinstance(node_output, dict) and "images" in node_output:
                for img in node_output["images"]:
                    output_images.append(img)
        
        if not output_images:
            raise HTTPException(status_code=500, detail="출력 이미지가 없습니다")
        
        img_info = output_images[0]
        img_bytes = await client.get_image(
            img_info["filename"],
            img_info.get("subfolder", ""),
            img_info.get("type", "output")
        )
        
        # 세션 폴더에 저장
        output_filename = request.output_filename or "edited.png"
        if not output_filename.endswith(".png"):
            output_filename += ".png"
        output_path = os.path.join(session_dir, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageEditResponse(
            success=True,
            output_file=output_filename,
            message=f"세션 '{request.session_id}'에 이미지 저장 완료",
            processing_time=round(processing_time, 2),
            session_id=request.session_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] /session/edit 실패:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"이미지 편집 실패: {str(e)}")


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
    filepath = os.path.join(SHARED_DIR, session_id, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    return FileResponse(filepath, media_type="image/png", filename=filename)


# ============================================
# 출력 엔드포인트
# ============================================
@app.get("/output/{filename}", tags=["Output"])
async def get_output(filename: str):
    """결과 이미지 다운로드"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    return FileResponse(filepath, media_type="image/png", filename=filename)


@app.get("/outputs", tags=["Output"])
async def list_outputs():
    """결과 이미지 목록"""
    files = []
    for f in Path(OUTPUT_DIR).glob("*.png"):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
    files.sort(key=lambda x: x["created"], reverse=True)
    return {"files": files, "count": len(files)}


# ============================================
# 메인 실행
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4100)
