"""
Z-Image Turbo API
ComfyUI를 통한 텍스트 → 이미지 생성 API
"""

from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import FileResponse, Response
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
    title="Z-Image Turbo API",
    description="ComfyUI 기반 텍스트 → 이미지 생성 API (Z-Image Turbo)",
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
WORKFLOW_PATH = os.getenv("WORKFLOW_PATH", "workflows/z_image_turbo_example.json")

OUTPUT_DIR = "outputs"
WORKFLOW_DIR = "workflows"
SHARED_DIR = "shared"

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


def get_session_dir(session_id: str) -> str:
    """세션 디렉토리 경로 반환 (없으면 생성)"""
    session_dir = os.path.join(SHARED_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


# ============================================
# Pydantic 모델
# ============================================
class ImageGenerateRequest(BaseModel):
    """이미지 생성 요청"""
    prompt: str = Field(..., description="이미지 생성 프롬프트")
    negative_prompt: Optional[str] = Field("blurry ugly bad", description="네거티브 프롬프트")
    width: Optional[int] = Field(1024, ge=512, le=2048, description="이미지 너비")
    height: Optional[int] = Field(1024, ge=512, le=2048, description="이미지 높이")
    steps: Optional[int] = Field(9, ge=1, le=50, description="샘플링 스텝 수")
    cfg: Optional[float] = Field(1.0, ge=0.1, le=20.0, description="CFG 스케일")
    seed: Optional[int] = Field(None, description="랜덤 시드 (없으면 자동 생성)")


class SessionImageGenerateRequest(BaseModel):
    """세션 기반 이미지 생성 요청"""
    session_id: str = Field(..., description="세션 ID")
    prompt: str = Field(..., description="이미지 생성 프롬프트")
    negative_prompt: Optional[str] = Field("blurry ugly bad", description="네거티브 프롬프트")
    output_filename: Optional[str] = Field("generated.png", description="출력 파일명")
    width: Optional[int] = Field(1024, ge=512, le=2048, description="이미지 너비")
    height: Optional[int] = Field(1024, ge=512, le=2048, description="이미지 높이")
    steps: Optional[int] = Field(9, ge=1, le=50, description="샘플링 스텝 수")
    cfg: Optional[float] = Field(1.0, ge=0.1, le=20.0, description="CFG 스케일")
    seed: Optional[int] = Field(None, description="랜덤 시드")


class ImageGenerateResponse(BaseModel):
    """이미지 생성 응답"""
    success: bool
    output_file: str
    message: str
    processing_time: float
    seed: int
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
    print(f"Z-Image Turbo API 시작...")
    print(f"ComfyUI URL: {COMFYUI_URL}")
    print(f"Workflow Path: {WORKFLOW_PATH}")
    
    cleanup_old_files(OUTPUT_DIR)
    
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
        "message": "Z-Image Turbo API",
        "version": "1.0.0",
        "description": "텍스트 프롬프트로 이미지를 생성합니다 (Z-Image Turbo)",
        "endpoints": {
            "POST /generate": "이미지 생성 (Form-data)",
            "POST /generate/json": "이미지 생성 (JSON)",
            "POST /session/generate": "세션 기반 이미지 생성",
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


@app.post("/generate", response_model=ImageGenerateResponse, tags=["Generate"])
async def generate_image_form(
    prompt: str = Form(..., description="이미지 생성 프롬프트"),
    negative_prompt: Optional[str] = Form("blurry ugly bad", description="네거티브 프롬프트"),
    width: Optional[int] = Form(1024, description="이미지 너비"),
    height: Optional[int] = Form(1024, description="이미지 높이"),
    steps: Optional[int] = Form(9, description="샘플링 스텝 수"),
    cfg: Optional[float] = Form(1.0, description="CFG 스케일"),
    seed: Optional[int] = Form(None, description="랜덤 시드"),
):
    """
    텍스트 프롬프트로 이미지 생성 (Form-data)
    """
    start_time = time.time()
    
    try:
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        # 시드 설정
        if seed is None:
            import random
            seed = random.randint(0, 2**32 - 1)
        
        # 워크플로우 업데이트
        workflow = client.update_image_workflow(
            workflow,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=seed
        )
        
        # 실행
        result = await client.execute_workflow(workflow, timeout=300)
        
        # 결과 이미지 가져오기
        outputs = result.get("outputs", {})
        output_images = []
        
        for node_id, node_output in outputs.items():
            if isinstance(node_output, dict) and "images" in node_output:
                for img in node_output["images"]:
                    output_images.append(img)
        
        if not output_images:
            raise HTTPException(status_code=500, detail="출력 이미지가 없습니다")
        
        # 첫 번째 이미지 저장
        img_info = output_images[0]
        img_bytes = await client.get_image(
            img_info["filename"],
            img_info.get("subfolder", ""),
            img_info.get("type", "output")
        )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        output_filename = f"zimage_{timestamp}_{unique_id}.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageGenerateResponse(
            success=True,
            output_file=output_filename,
            message="이미지 생성 완료",
            processing_time=round(processing_time, 2),
            seed=seed
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] 이미지 생성 실패:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"이미지 생성 실패: {str(e)}")


@app.post("/generate/json", response_model=ImageGenerateResponse, tags=["Generate"])
async def generate_image_json(request: ImageGenerateRequest):
    """
    텍스트 프롬프트로 이미지 생성 (JSON)
    """
    start_time = time.time()
    
    try:
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        seed = request.seed
        if seed is None:
            import random
            seed = random.randint(0, 2**32 - 1)
        
        workflow = client.update_image_workflow(
            workflow,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg=request.cfg,
            seed=seed
        )
        
        result = await client.execute_workflow(workflow, timeout=300)
        
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
        output_filename = f"zimage_{timestamp}_{unique_id}.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageGenerateResponse(
            success=True,
            output_file=output_filename,
            message="이미지 생성 완료",
            processing_time=round(processing_time, 2),
            seed=seed
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"이미지 생성 실패: {str(e)}")


# ============================================
# 세션 기반 엔드포인트
# ============================================
@app.post("/session/generate", response_model=ImageGenerateResponse, tags=["Session"])
async def session_generate_image(request: SessionImageGenerateRequest):
    """
    세션 기반 이미지 생성
    
    결과 이미지가 세션 폴더에 저장됩니다.
    """
    start_time = time.time()
    
    try:
        session_dir = get_session_dir(request.session_id)
        
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        seed = request.seed
        if seed is None:
            import random
            seed = random.randint(0, 2**32 - 1)
        
        workflow = client.update_image_workflow(
            workflow,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg=request.cfg,
            seed=seed
        )
        
        result = await client.execute_workflow(workflow, timeout=300)
        
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
        
        output_filename = request.output_filename or "generated.png"
        if not output_filename.endswith(".png"):
            output_filename += ".png"
        output_path = os.path.join(session_dir, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageGenerateResponse(
            success=True,
            output_file=output_filename,
            message=f"세션 '{request.session_id}'에 이미지 저장 완료",
            processing_time=round(processing_time, 2),
            seed=seed,
            session_id=request.session_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"이미지 생성 실패: {str(e)}")


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
# 출력 엔드포인트
# ============================================
@app.get("/output/{filename}", tags=["Output"])
async def get_output(filename: str):
    """결과 이미지 다운로드"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    return FileResponse(
        filepath,
        media_type="image/png",
        filename=filename
    )


@app.delete("/output/{filename}", tags=["Output"])
async def delete_output(filename: str):
    """결과 이미지 삭제"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    os.remove(filepath)
    return {"success": True, "message": f"{filename} 삭제 완료"}


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
    uvicorn.run(app, host="0.0.0.0", port=4400)

