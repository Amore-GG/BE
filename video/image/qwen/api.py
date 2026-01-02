"""
Qwen Image Edit API
ComfyUI를 통한 이미지 편집 API
- 기본 지지(GiGi) 얼굴 이미지 내장
- v2 워크플로우: 최대 3개 이미지 지원
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
import shutil
from datetime import datetime
from pathlib import Path

from comfyui_client import ComfyUIClient

# ============================================
# FastAPI 앱 초기화
# ============================================
app = FastAPI(
    title="Qwen Image Edit API",
    description="ComfyUI 기반 이미지 편집 API - 기본 지지(GiGi) 얼굴 내장",
    version="2.1.0"
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
WORKFLOW_PATH = os.getenv("WORKFLOW_PATH", "workflows/image_qwen_image_edit_2509_v2.json")

OUTPUT_DIR = "outputs"
UPLOAD_DIR = "uploads"
SHARED_DIR = "shared"
ASSETS_DIR = "assets"  # 기본 이미지 저장 폴더

# 기본 얼굴 이미지 설정
DEFAULT_FACE_FILENAME = "default_face.png"
DEFAULT_FACE_PATH = os.path.join(ASSETS_DIR, DEFAULT_FACE_FILENAME)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# ComfyUI 클라이언트
client = ComfyUIClient(COMFYUI_URL)

# 파일 자동 삭제 설정
FILE_MAX_AGE_HOURS = 2

# 기본 얼굴 이미지 ComfyUI 업로드 상태
default_face_uploaded = False


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


async def ensure_default_face_uploaded():
    """기본 얼굴 이미지가 ComfyUI에 업로드되었는지 확인하고 업로드"""
    global default_face_uploaded
    
    if not os.path.exists(DEFAULT_FACE_PATH):
        print(f"[Warning] 기본 얼굴 이미지 없음: {DEFAULT_FACE_PATH}")
        return False
    
    if not default_face_uploaded:
        try:
            await client.upload_image(DEFAULT_FACE_PATH, DEFAULT_FACE_FILENAME)
            default_face_uploaded = True
            print(f"[Default Face] ComfyUI에 업로드 완료: {DEFAULT_FACE_FILENAME}")
        except Exception as e:
            print(f"[Default Face] 업로드 실패: {e}")
            return False
    
    return True


# ============================================
# Pydantic 모델
# ============================================
class ImageEditRequest(BaseModel):
    """이미지 편집 요청 (JSON) - v2: 3개 이미지 지원"""
    prompt: str = Field(..., description="편집 프롬프트")
    image1_filename: str = Field(..., description="첫 번째 이미지 파일명 (메인 이미지)")
    image2_filename: Optional[str] = Field(None, description="두 번째 이미지 파일명 (참조 이미지1)")
    image3_filename: Optional[str] = Field(None, description="세 번째 이미지 파일명 (참조 이미지2)")


class GigiEditRequest(BaseModel):
    """지지 얼굴 기반 이미지 편집 요청 (기본 얼굴 자동 적용)"""
    prompt: str = Field(..., description="편집 프롬프트 (포즈, 표정, 스타일 등)")
    style_image_filename: Optional[str] = Field(None, description="스타일 참조 이미지 (선택)")
    pose_image_filename: Optional[str] = Field(None, description="포즈 참조 이미지 (선택)")


class SessionGigiEditRequest(BaseModel):
    """세션 기반 지지 얼굴 편집 요청"""
    session_id: str = Field(..., description="세션 ID")
    prompt: str = Field(..., description="편집 프롬프트")
    style_image_filename: Optional[str] = Field(None, description="세션 내 스타일 참조 이미지")
    pose_image_filename: Optional[str] = Field(None, description="세션 내 포즈 참조 이미지")
    output_filename: Optional[str] = Field("gigi_styled.png", description="출력 파일명")


class SessionImageEditRequest(BaseModel):
    """세션 기반 이미지 편집 요청 - v2: 3개 이미지 지원"""
    session_id: str = Field(..., description="세션 ID")
    prompt: str = Field(..., description="편집 프롬프트")
    image1_filename: str = Field(..., description="세션 내 첫 번째 이미지 파일명 (메인 이미지)")
    image2_filename: Optional[str] = Field(None, description="세션 내 두 번째 이미지 파일명 (참조 이미지1)")
    image3_filename: Optional[str] = Field(None, description="세션 내 세 번째 이미지 파일명 (참조 이미지2)")
    output_filename: Optional[str] = Field("edited.png", description="출력 파일명")


class ImageEditResponse(BaseModel):
    """이미지 편집 응답"""
    success: bool
    output_file: str
    message: str
    processing_time: float
    session_id: Optional[str] = None
    used_default_face: bool = False


class DefaultFaceResponse(BaseModel):
    """기본 얼굴 이미지 정보"""
    exists: bool
    filename: str
    path: str
    size_mb: Optional[float] = None
    uploaded_to_comfyui: bool


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    status: str
    comfyui_url: str
    comfyui_connected: bool
    workflow_exists: bool
    default_face_exists: bool


# ============================================
# 이벤트 핸들러
# ============================================
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    print(f"Qwen Image Edit API v2.1 시작...")
    print(f"ComfyUI URL: {COMFYUI_URL}")
    print(f"Workflow Path: {WORKFLOW_PATH}")
    print(f"Default Face Path: {DEFAULT_FACE_PATH}")
    
    cleanup_old_files(OUTPUT_DIR)
    cleanup_old_files(UPLOAD_DIR)
    
    asyncio.create_task(periodic_cleanup())
    print(f"[Cleanup] 자동 파일 정리 활성화 ({FILE_MAX_AGE_HOURS}시간 이상 파일 삭제)")
    
    if os.path.exists(WORKFLOW_PATH):
        print(f"워크플로우 파일 확인됨: {WORKFLOW_PATH}")
    else:
        print(f"경고: 워크플로우 파일이 없습니다: {WORKFLOW_PATH}")
    
    # 기본 얼굴 이미지 확인
    if os.path.exists(DEFAULT_FACE_PATH):
        print(f"[Default Face] 기본 얼굴 이미지 확인됨: {DEFAULT_FACE_PATH}")
        # 서버 시작 시 ComfyUI에 업로드 시도 (실패해도 계속 진행)
        try:
            await ensure_default_face_uploaded()
        except Exception as e:
            print(f"[Default Face] 초기 업로드 실패 (나중에 재시도): {e}")
    else:
        print(f"[Default Face] 경고: 기본 얼굴 이미지 없음 - /default-face API로 업로드하세요")


# ============================================
# API 엔드포인트
# ============================================
@app.get("/", tags=["Root"])
async def root():
    """API 루트"""
    return {
        "message": "Qwen Image Edit API",
        "version": "2.1.0",
        "description": "기본 지지(GiGi) 얼굴 내장 + v2 워크플로우",
        "endpoints": {
            "POST /edit/gigi": "⭐ 지지 얼굴 기반 편집 (기본 얼굴 자동 적용)",
            "POST /session/edit/gigi": "⭐ 세션 기반 지지 얼굴 편집",
            "POST /edit": "이미지 편집 (Form-data, 3개 이미지)",
            "POST /edit/json": "이미지 편집 (JSON)",
            "POST /session/edit": "세션 기반 이미지 편집",
            "GET /default-face": "기본 얼굴 이미지 확인",
            "POST /default-face": "기본 얼굴 이미지 업로드",
            "GET /health": "헬스 체크"
        },
        "gigi_mode": {
            "description": "지지 얼굴을 기본으로 사용하여 편집",
            "image1": "자동으로 기본 지지 얼굴 사용",
            "image2": "스타일 참조 이미지 (선택)",
            "image3": "포즈 참조 이미지 (선택)"
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
        workflow_exists=os.path.exists(WORKFLOW_PATH),
        default_face_exists=os.path.exists(DEFAULT_FACE_PATH)
    )


# ============================================
# 기본 얼굴 이미지 관리 API
# ============================================
@app.get("/default-face", response_model=DefaultFaceResponse, tags=["Default Face"])
async def get_default_face():
    """기본 얼굴 이미지 정보 확인"""
    exists = os.path.exists(DEFAULT_FACE_PATH)
    size_mb = None
    
    if exists:
        size_mb = round(os.path.getsize(DEFAULT_FACE_PATH) / (1024 * 1024), 2)
    
    return DefaultFaceResponse(
        exists=exists,
        filename=DEFAULT_FACE_FILENAME,
        path=DEFAULT_FACE_PATH,
        size_mb=size_mb,
        uploaded_to_comfyui=default_face_uploaded
    )


@app.post("/default-face", tags=["Default Face"])
async def upload_default_face(
    image: UploadFile = File(..., description="기본 얼굴 이미지 (지지 사진)")
):
    """기본 얼굴 이미지 업로드 (지지 사진 설정)"""
    global default_face_uploaded
    
    try:
        # 파일 저장
        content = await image.read()
        with open(DEFAULT_FACE_PATH, "wb") as f:
            f.write(content)
        
        # ComfyUI에 업로드
        await client.upload_image(DEFAULT_FACE_PATH, DEFAULT_FACE_FILENAME)
        default_face_uploaded = True
        
        size_mb = round(len(content) / (1024 * 1024), 2)
        
        return {
            "success": True,
            "message": "기본 얼굴 이미지(지지) 설정 완료",
            "filename": DEFAULT_FACE_FILENAME,
            "size_mb": size_mb,
            "uploaded_to_comfyui": True
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


@app.get("/default-face/image", tags=["Default Face"])
async def download_default_face():
    """기본 얼굴 이미지 다운로드"""
    if not os.path.exists(DEFAULT_FACE_PATH):
        raise HTTPException(status_code=404, detail="기본 얼굴 이미지가 설정되지 않았습니다")
    
    return FileResponse(DEFAULT_FACE_PATH, media_type="image/png", filename=DEFAULT_FACE_FILENAME)


# ============================================
# 지지 얼굴 기반 편집 엔드포인트 (핵심!)
# ============================================
@app.post("/edit/gigi", response_model=ImageEditResponse, tags=["GiGi Edit"])
async def edit_with_gigi_face(
    prompt: str = Form(..., description="편집 프롬프트 (포즈, 표정, 스타일 등)"),
    style_image: Optional[UploadFile] = File(None, description="스타일 참조 이미지 (선택)"),
    pose_image: Optional[UploadFile] = File(None, description="포즈 참조 이미지 (선택)"),
):
    """
    ⭐ 지지 얼굴 기반 이미지 편집
    
    - **image1**: 자동으로 기본 지지 얼굴 사용
    - **style_image**: 스타일 참조 이미지 (헤어, 메이크업, 옷 등)
    - **pose_image**: 포즈 참조 이미지
    """
    start_time = time.time()
    
    try:
        # 기본 얼굴 이미지 확인
        if not os.path.exists(DEFAULT_FACE_PATH):
            raise HTTPException(
                status_code=400, 
                detail="기본 얼굴 이미지가 설정되지 않았습니다. POST /default-face로 먼저 업로드하세요."
            )
        
        # ComfyUI에 기본 얼굴 업로드 확인
        await ensure_default_face_uploaded()
        
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        unique_id = str(uuid.uuid4())[:8]
        
        # Image 2 (스타일 참조) 처리
        image2_filename = None
        if style_image and style_image.filename:
            ext2 = os.path.splitext(style_image.filename)[1] or ".png"
            image2_filename = f"gigi_{unique_id}_style{ext2}"
            image2_path = os.path.join(UPLOAD_DIR, image2_filename)
            with open(image2_path, "wb") as f:
                f.write(await style_image.read())
            await client.upload_image(image2_path, image2_filename)
        
        # Image 3 (포즈 참조) 처리
        image3_filename = None
        if pose_image and pose_image.filename:
            ext3 = os.path.splitext(pose_image.filename)[1] or ".png"
            image3_filename = f"gigi_{unique_id}_pose{ext3}"
            image3_path = os.path.join(UPLOAD_DIR, image3_filename)
            with open(image3_path, "wb") as f:
                f.write(await pose_image.read())
            await client.upload_image(image3_path, image3_filename)
        
        # 워크플로우 업데이트 (image1 = 기본 지지 얼굴)
        workflow = client.update_workflow_images(
            workflow, 
            DEFAULT_FACE_FILENAME,  # 항상 기본 지지 얼굴 사용
            image2_filename, 
            image3_filename
        )
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
        output_filename = f"gigi_{timestamp}_{unique_id}.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageEditResponse(
            success=True,
            output_file=output_filename,
            message="지지 얼굴 기반 이미지 편집 완료",
            processing_time=round(processing_time, 2),
            used_default_face=True
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] /edit/gigi 실패:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"이미지 편집 실패: {str(e)}")


@app.post("/session/edit/gigi", response_model=ImageEditResponse, tags=["GiGi Edit"])
async def session_edit_with_gigi_face(request: SessionGigiEditRequest):
    """
    ⭐ 세션 기반 지지 얼굴 편집
    
    - 기본 지지 얼굴 자동 적용
    - 세션 폴더 내 참조 이미지 사용 가능
    - 결과도 세션 폴더에 저장
    """
    start_time = time.time()
    
    try:
        session_dir = get_session_dir(request.session_id)
        
        # 기본 얼굴 이미지 확인
        if not os.path.exists(DEFAULT_FACE_PATH):
            raise HTTPException(
                status_code=400, 
                detail="기본 얼굴 이미지가 설정되지 않았습니다."
            )
        
        await ensure_default_face_uploaded()
        
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        # Image 2 (스타일 참조) 처리
        image2_filename = None
        if request.style_image_filename:
            image2_path = os.path.join(session_dir, request.style_image_filename)
            if not os.path.exists(image2_path):
                raise HTTPException(status_code=404, detail=f"스타일 이미지를 찾을 수 없습니다: {request.style_image_filename}")
            await client.upload_image(image2_path, request.style_image_filename)
            image2_filename = request.style_image_filename
        
        # Image 3 (포즈 참조) 처리
        image3_filename = None
        if request.pose_image_filename:
            image3_path = os.path.join(session_dir, request.pose_image_filename)
            if not os.path.exists(image3_path):
                raise HTTPException(status_code=404, detail=f"포즈 이미지를 찾을 수 없습니다: {request.pose_image_filename}")
            await client.upload_image(image3_path, request.pose_image_filename)
            image3_filename = request.pose_image_filename
        
        # 워크플로우 업데이트 (image1 = 기본 지지 얼굴)
        workflow = client.update_workflow_images(
            workflow, 
            DEFAULT_FACE_FILENAME,
            image2_filename, 
            image3_filename
        )
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
        output_filename = request.output_filename or "gigi_styled.png"
        if not output_filename.endswith(".png"):
            output_filename += ".png"
        output_path = os.path.join(session_dir, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        
        processing_time = time.time() - start_time
        
        return ImageEditResponse(
            success=True,
            output_file=output_filename,
            message=f"세션 '{request.session_id}'에 지지 이미지 저장 완료",
            processing_time=round(processing_time, 2),
            session_id=request.session_id,
            used_default_face=True
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] /session/edit/gigi 실패:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"이미지 편집 실패: {str(e)}")


# ============================================
# 일반 편집 엔드포인트 (기존 유지)
# ============================================
@app.post("/edit", response_model=ImageEditResponse, tags=["Edit"])
async def edit_image_form(
    prompt: str = Form(..., description="편집 프롬프트"),
    image1: UploadFile = File(..., description="첫 번째 이미지 (메인)"),
    image2: Optional[UploadFile] = File(None, description="두 번째 이미지 (참조1)"),
    image3: Optional[UploadFile] = File(None, description="세 번째 이미지 (참조2)"),
):
    """이미지 편집 (Form-data) - 이미지 직접 업로드"""
    start_time = time.time()
    
    try:
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        unique_id = str(uuid.uuid4())[:8]
        
        # Image 1
        ext1 = os.path.splitext(image1.filename)[1] or ".png"
        image1_filename = f"edit_{unique_id}_1{ext1}"
        image1_path = os.path.join(UPLOAD_DIR, image1_filename)
        with open(image1_path, "wb") as f:
            f.write(await image1.read())
        await client.upload_image(image1_path, image1_filename)
        
        # Image 2
        image2_filename = None
        if image2 and image2.filename:
            ext2 = os.path.splitext(image2.filename)[1] or ".png"
            image2_filename = f"edit_{unique_id}_2{ext2}"
            image2_path = os.path.join(UPLOAD_DIR, image2_filename)
            with open(image2_path, "wb") as f:
                f.write(await image2.read())
            await client.upload_image(image2_path, image2_filename)
        
        # Image 3
        image3_filename = None
        if image3 and image3.filename:
            ext3 = os.path.splitext(image3.filename)[1] or ".png"
            image3_filename = f"edit_{unique_id}_3{ext3}"
            image3_path = os.path.join(UPLOAD_DIR, image3_filename)
            with open(image3_path, "wb") as f:
                f.write(await image3.read())
            await client.upload_image(image3_path, image3_filename)
        
        workflow = client.update_workflow_images(workflow, image1_filename, image2_filename, image3_filename)
        workflow = client.update_workflow_prompt(workflow, prompt)
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
    """이미지 편집 (JSON) - 미리 업로드된 이미지 사용"""
    start_time = time.time()
    
    try:
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        workflow = client.update_workflow_images(
            workflow,
            request.image1_filename,
            request.image2_filename,
            request.image3_filename
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
    """세션 기반 이미지 편집 (v2: 최대 3개 이미지)"""
    start_time = time.time()
    
    try:
        session_dir = get_session_dir(request.session_id)
        
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        # Image 1
        image1_path = os.path.join(session_dir, request.image1_filename)
        if not os.path.exists(image1_path):
            raise HTTPException(status_code=404, detail=f"이미지를 찾을 수 없습니다: {request.image1_filename}")
        await client.upload_image(image1_path, request.image1_filename)
        
        # Image 2
        image2_filename = None
        if request.image2_filename:
            image2_path = os.path.join(session_dir, request.image2_filename)
            if not os.path.exists(image2_path):
                raise HTTPException(status_code=404, detail=f"이미지를 찾을 수 없습니다: {request.image2_filename}")
            await client.upload_image(image2_path, request.image2_filename)
            image2_filename = request.image2_filename
        
        # Image 3
        image3_filename = None
        if request.image3_filename:
            image3_path = os.path.join(session_dir, request.image3_filename)
            if not os.path.exists(image3_path):
                raise HTTPException(status_code=404, detail=f"이미지를 찾을 수 없습니다: {request.image3_filename}")
            await client.upload_image(image3_path, request.image3_filename)
            image3_filename = request.image3_filename
        
        workflow = client.update_workflow_images(workflow, request.image1_filename, image2_filename, image3_filename)
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
