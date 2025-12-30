"""
Wan2.1 Image-to-Video API
ComfyUI를 통한 이미지 → 영상 생성 API
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import uuid
import time
import asyncio
import shutil
from datetime import datetime
from pathlib import Path

from comfyui_client import ComfyUIClient

# FastAPI 앱 초기화
app = FastAPI(
    title="Wan2 Image-to-Video API",
    description="ComfyUI 기반 이미지 → 비디오 생성 API (Wan2.1 14B)",
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

# 환경변수
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8000")
WORKFLOW_PATH = os.getenv("WORKFLOW_PATH", "workflows/GG_wan2_2_14B_i2v(1).json")

# 디렉토리 설정
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
WORKFLOW_DIR = "workflows"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WORKFLOW_DIR, exist_ok=True)

# ComfyUI 클라이언트
client = ComfyUIClient(COMFYUI_URL)

# 파일 자동 삭제 설정
FILE_MAX_AGE_HOURS = 1


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


class I2VRequest(BaseModel):
    """이미지 → 비디오 요청 (JSON Body용)"""
    prompt: str = Field(..., description="영상 생성 프롬프트")
    image_filename: str = Field(..., description="입력 이미지 파일명 (업로드된)")
    width: Optional[int] = Field(512, description="영상 너비 (기본: 512)")
    height: Optional[int] = Field(512, description="영상 높이 (기본: 512)")
    length: Optional[int] = Field(121, description="프레임 수 (기본: 121, 약 6초)")
    steps: Optional[int] = Field(8, description="샘플링 스텝 (기본: 8)")
    cfg: Optional[float] = Field(1.0, description="CFG 스케일 (기본: 1.0)")


class I2VResponse(BaseModel):
    """이미지 → 비디오 응답"""
    success: bool
    output_file: str
    message: str
    processing_time: float


class UploadResponse(BaseModel):
    """업로드 응답"""
    success: bool
    filename: str
    message: str


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    print(f"Wan2 Image-to-Video API 시작...")
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


@app.get("/")
async def root():
    """API 루트"""
    return {
        "message": "Wan2 Image-to-Video API",
        "version": "1.0.0",
        "description": "이미지를 입력받아 영상을 생성합니다 (Wan2.1 14B 모델)",
        "endpoints": {
            "POST /upload": "이미지 업로드",
            "POST /generate": "영상 생성 (Form-data)",
            "POST /generate/json": "영상 생성 (JSON)",
            "GET /output/{filename}": "결과 영상 다운로드",
            "GET /health": "헬스 체크"
        }
    }


@app.get("/health")
async def health_check():
    """헬스 체크"""
    # ComfyUI 연결 확인
    comfyui_ok = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.get(f"{COMFYUI_URL}/system_stats")
            comfyui_ok = response.status_code == 200
    except:
        pass
    
    return {
        "status": "healthy",
        "comfyui_url": COMFYUI_URL,
        "comfyui_connected": comfyui_ok,
        "workflow_exists": os.path.exists(WORKFLOW_PATH)
    }


@app.post("/upload", response_model=UploadResponse)
async def upload_image(
    image: UploadFile = File(..., description="업로드할 이미지")
):
    """이미지 업로드"""
    try:
        # 고유 파일명 생성
        ext = os.path.splitext(image.filename)[1] or ".png"
        unique_id = str(uuid.uuid4())[:8]
        filename = f"upload_{unique_id}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        # 파일 저장
        with open(filepath, "wb") as f:
            content = await image.read()
            f.write(content)
        
        # ComfyUI에도 업로드
        try:
            comfy_filename = await client.upload_image(filepath, filename)
        except Exception as e:
            print(f"ComfyUI 업로드 실패 (나중에 재시도): {e}")
            comfy_filename = filename
        
        return UploadResponse(
            success=True,
            filename=filename,
            message="이미지 업로드 완료"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


@app.post("/generate", response_model=I2VResponse)
async def generate_video_form(
    image: UploadFile = File(..., description="입력 이미지"),
    prompt: str = Form(..., description="영상 생성 프롬프트"),
    width: Optional[int] = Form(512, description="영상 너비"),
    height: Optional[int] = Form(512, description="영상 높이"),
    length: Optional[int] = Form(121, description="프레임 수 (약 6초)"),
    steps: Optional[int] = Form(8, description="샘플링 스텝"),
    cfg: Optional[float] = Form(1.0, description="CFG 스케일"),
):
    """
    이미지 → 비디오 생성 (Form-data)
    
    - **image**: 입력 이미지 (필수)
    - **prompt**: 영상 생성 프롬프트 (예: "The character walks forward slowly")
    - **width**: 영상 너비 (기본: 512)
    - **height**: 영상 높이 (기본: 512)
    - **length**: 프레임 수 (기본: 121, 약 6초 @ 20fps)
    - **steps**: 샘플링 스텝 (기본: 8, 높을수록 품질↑ 속도↓)
    - **cfg**: CFG 스케일 (기본: 1.0)
    """
    start_time = time.time()
    
    try:
        # 워크플로우 로드
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        # 워크플로우 노드 확인 (디버깅)
        node_ids = list(workflow.keys())
        print(f"[Workflow] 로드된 노드 수: {len(node_ids)}")
        print(f"[Workflow] 노드 목록: {node_ids}")
        
        # 문제가 되는 노드 확인
        problem_nodes = ['194', '195', '202', '230', '231', '81', '82', '83']
        found_problems = [n for n in problem_nodes if n in node_ids]
        if found_problems:
            print(f"[WARNING] 문제 노드 발견! {found_problems}")
            print(f"[WARNING] Docker 재빌드가 필요합니다!")
        else:
            print(f"[Workflow] OK - 불필요한 노드 없음 (PreviewImage 등 제거됨)")
        
        # 이미지 저장 및 업로드
        unique_id = str(uuid.uuid4())[:8]
        
        ext = os.path.splitext(image.filename)[1] or ".png"
        image_filename = f"i2v_{unique_id}{ext}"
        image_path = os.path.join(UPLOAD_DIR, image_filename)
        with open(image_path, "wb") as f:
            f.write(await image.read())
        
        await client.upload_image(image_path, image_filename)
        
        # 워크플로우 업데이트
        workflow = client.update_i2v_workflow(
            workflow,
            image_filename=image_filename,
            prompt=prompt,
            width=width,
            height=height,
            length=length,
            steps=steps,
            cfg=cfg
        )
        workflow = client.randomize_seed(workflow)  # seed 랜덤화
        
        # 실행 (영상 생성은 오래 걸림 - 타임아웃 30분)
        result = await client.execute_workflow(workflow, timeout=1800)
        
        # 디버깅: 전체 결과 출력
        print(f"[Debug] Full result keys: {result.keys()}")
        print(f"[Debug] Result: {result}")
        
        # 결과 비디오 가져오기
        outputs = result.get("outputs", {})
        print(f"[Debug] Outputs: {outputs}")
        
        output_videos = []
        
        for node_id, node_output in outputs.items():
            print(f"[Debug] Node {node_id} output keys: {node_output.keys() if isinstance(node_output, dict) else 'not dict'}")
            # VHS_VideoCombine 노드의 출력
            if "gifs" in node_output:
                for vid in node_output["gifs"]:
                    output_videos.append(vid)
                    print(f"[Debug] Found video: {vid}")
        
        if not output_videos:
            # 추가 디버깅: images로 출력되는 경우도 체크
            for node_id, node_output in outputs.items():
                if isinstance(node_output, dict):
                    if "images" in node_output:
                        print(f"[Debug] Node {node_id} has images: {node_output['images']}")
            
            # 비디오 생성 노드 (68)가 실행되지 않은 경우 상세 오류 메시지
            error_msg = f"출력 비디오가 없습니다.\n"
            error_msg += f"실행된 노드: {list(outputs.keys())}\n"
            error_msg += f"비디오 생성 노드 (68)가 실행되지 않았습니다.\n"
            error_msg += f"ComfyUI 서버에서 다음 모델들이 있는지 확인하세요:\n"
            error_msg += f"- wan2.2_i2v_high_noise_14B_Q5_K_S.gguf\n"
            error_msg += f"- wan2.2_i2v_low_noise_14B_Q5_K_S.gguf\n"
            error_msg += f"- wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors\n"
            error_msg += f"- wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors\n"
            error_msg += f"ComfyUI 웹에서 직접 워크플로우를 실행해서 오류를 확인하세요."
            raise HTTPException(status_code=500, detail=error_msg)
        
        # 첫 번째 출력 비디오 저장
        vid_info = output_videos[0]
        vid_bytes = await client.get_video(
            vid_info["filename"],
            vid_info.get("subfolder", ""),
            vid_info.get("type", "output")
        )
        
        # 로컬에 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"i2v_{timestamp}_{unique_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(vid_bytes)
        
        processing_time = time.time() - start_time
        
        return I2VResponse(
            success=True,
            output_file=output_filename,
            message="영상 생성 완료",
            processing_time=round(processing_time, 2)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] /generate 영상 생성 실패:")
        print(error_trace)
        raise HTTPException(status_code=500, detail=f"영상 생성 실패: {str(e) or type(e).__name__}")


@app.post("/generate/json", response_model=I2VResponse)
async def generate_video_json(request: I2VRequest):
    """
    이미지 → 비디오 생성 (JSON) - 미리 업로드된 이미지 사용
    """
    start_time = time.time()
    
    try:
        # 워크플로우 로드
        if not os.path.exists(WORKFLOW_PATH):
            raise HTTPException(status_code=500, detail="워크플로우 파일이 없습니다")
        
        workflow = client.load_workflow(WORKFLOW_PATH)
        
        # 워크플로우 업데이트
        workflow = client.update_i2v_workflow(
            workflow,
            image_filename=request.image_filename,
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            length=request.length,
            steps=request.steps,
            cfg=request.cfg
        )
        workflow = client.randomize_seed(workflow)  # seed 랜덤화
        
        # 실행
        result = await client.execute_workflow(workflow, timeout=1800)
        
        # 결과 처리
        outputs = result.get("outputs", {})
        output_videos = []
        
        for node_id, node_output in outputs.items():
            if "gifs" in node_output:
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
        output_filename = f"i2v_{timestamp}_{unique_id}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(output_path, "wb") as f:
            f.write(vid_bytes)
        
        processing_time = time.time() - start_time
        
        return I2VResponse(
            success=True,
            output_file=output_filename,
            message="영상 생성 완료",
            processing_time=round(processing_time, 2)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] /generate/json 영상 생성 실패:")
        print(error_trace)
        raise HTTPException(status_code=500, detail=f"영상 생성 실패: {str(e) or type(e).__name__}")


@app.get("/output/{filename}")
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


@app.delete("/output/{filename}")
async def delete_output(filename: str):
    """결과 영상 삭제"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    os.remove(filepath)
    return {"success": True, "message": f"{filename} 삭제 완료"}


@app.get("/outputs")
async def list_outputs():
    """결과 영상 목록"""
    files = []
    for f in Path(OUTPUT_DIR).glob("*"):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
    return {"files": files, "count": len(files)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4200)

