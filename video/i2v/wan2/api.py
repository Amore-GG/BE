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
    project_id: Optional[str] = Field(None, description="프로젝트 ID (FE에서 스토리보드 구분용)")
    sequence: Optional[int] = Field(None, description="시퀀스 번호 (스토리보드 순서, 1부터 시작)")
    width: Optional[int] = Field(512, description="영상 너비 (기본: 512)")
    height: Optional[int] = Field(512, description="영상 높이 (기본: 512)")
    length: Optional[int] = Field(121, description="프레임 수 (기본: 121, 약 6초)")
    steps: Optional[int] = Field(8, description="샘플링 스텝 (기본: 8)")
    cfg: Optional[float] = Field(1.0, description="CFG 스케일 (기본: 1.0)")


class I2VResponse(BaseModel):
    """이미지 → 비디오 응답"""
    success: bool
    output_file: str
    project_id: Optional[str] = None
    sequence: Optional[int] = None
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
    project_id: Optional[str] = Form(None, description="프로젝트 ID (스토리보드 구분용)"),
    sequence: Optional[int] = Form(None, description="시퀀스 번호 (1부터 시작)"),
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
    - **project_id**: 프로젝트 ID (스토리보드 구분용, 예: "user123_story456")
    - **sequence**: 시퀀스 번호 (스토리보드 순서, 1부터 시작)
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
        problem_nodes = ['194', '195', '202', '230', '231', '81', '82', '83', '113']
        found_problems = [n for n in problem_nodes if n in node_ids]
        if found_problems:
            print(f"[WARNING] 문제 노드 발견! {found_problems}")
            print(f"[WARNING] Docker 재빌드가 필요합니다!")
        else:
            print(f"[Workflow] OK - 불필요한 노드 없음 (MathExpression, PreviewImage 등 제거됨)")
        
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
        
        # 로컬에 저장 (프로젝트별 폴더 구조)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if project_id:
            # 프로젝트 폴더 생성
            project_dir = os.path.join(OUTPUT_DIR, f"proj_{project_id}")
            os.makedirs(project_dir, exist_ok=True)
            
            # 시퀀스 번호가 있으면 순서대로 파일명 생성
            if sequence is not None:
                output_filename = f"scene_{sequence:03d}.mp4"
            else:
                output_filename = f"scene_{timestamp}_{unique_id}.mp4"
            
            output_path = os.path.join(project_dir, output_filename)
            # API 응답용 상대 경로
            relative_filename = f"proj_{project_id}/{output_filename}"
        else:
            # 프로젝트 ID 없으면 기존 방식
            output_filename = f"i2v_{timestamp}_{unique_id}.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            relative_filename = output_filename
        
        with open(output_path, "wb") as f:
            f.write(vid_bytes)
        
        processing_time = time.time() - start_time
        
        return I2VResponse(
            success=True,
            output_file=relative_filename,
            project_id=project_id,
            sequence=sequence,
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
        
        # 비디오 저장 (프로젝트별 폴더 구조)
        vid_info = output_videos[0]
        vid_bytes = await client.get_video(
            vid_info["filename"],
            vid_info.get("subfolder", ""),
            vid_info.get("type", "output")
        )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        if request.project_id:
            # 프로젝트 폴더 생성
            project_dir = os.path.join(OUTPUT_DIR, f"proj_{request.project_id}")
            os.makedirs(project_dir, exist_ok=True)
            
            # 시퀀스 번호가 있으면 순서대로 파일명 생성
            if request.sequence is not None:
                output_filename = f"scene_{request.sequence:03d}.mp4"
            else:
                output_filename = f"scene_{timestamp}_{unique_id}.mp4"
            
            output_path = os.path.join(project_dir, output_filename)
            relative_filename = f"proj_{request.project_id}/{output_filename}"
        else:
            output_filename = f"i2v_{timestamp}_{unique_id}.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            relative_filename = output_filename
        
        with open(output_path, "wb") as f:
            f.write(vid_bytes)
        
        processing_time = time.time() - start_time
        
        return I2VResponse(
            success=True,
            output_file=relative_filename,
            project_id=request.project_id,
            sequence=request.sequence,
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


@app.get("/output/{filename:path}")
async def get_output(filename: str):
    """
    결과 영상 다운로드
    
    - filename: 파일명 또는 프로젝트 경로 (예: "i2v_xxx.mp4" 또는 "proj_abc123/scene_001.mp4")
    """
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    # 파일명만 추출 (다운로드용)
    download_name = os.path.basename(filename)
    
    return FileResponse(
        filepath,
        media_type="video/mp4",
        filename=download_name
    )


@app.delete("/output/{filename:path}")
async def delete_output(filename: str):
    """결과 영상 삭제 (프로젝트 경로 지원)"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    os.remove(filepath)
    return {"success": True, "message": f"{filename} 삭제 완료"}


@app.get("/outputs")
async def list_outputs():
    """결과 영상 목록 (전체)"""
    files = []
    for f in Path(OUTPUT_DIR).glob("*"):
        if f.is_file():
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
    # 생성 시간 순으로 정렬
    files.sort(key=lambda x: x["created"])
    return {"files": files, "count": len(files)}


@app.get("/projects")
async def list_projects():
    """프로젝트 목록 조회"""
    projects = []
    for d in Path(OUTPUT_DIR).glob("proj_*"):
        if d.is_dir():
            project_id = d.name.replace("proj_", "")
            video_count = len(list(d.glob("*.mp4")))
            
            # 합쳐진 최종 영상 확인
            final_video = None
            for f in d.glob("final*.mp4"):
                final_video = f.name
                break
            
            projects.append({
                "project_id": project_id,
                "folder": d.name,
                "video_count": video_count,
                "final_video": final_video,
                "created": datetime.fromtimestamp(d.stat().st_ctime).isoformat()
            })
    
    projects.sort(key=lambda x: x["created"], reverse=True)
    return {"projects": projects, "count": len(projects)}


@app.get("/project/{project_id}/videos")
async def list_project_videos(project_id: str):
    """특정 프로젝트의 영상 목록 (시퀀스 순서대로)"""
    project_dir = os.path.join(OUTPUT_DIR, f"proj_{project_id}")
    
    if not os.path.exists(project_dir):
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    
    videos = []
    for f in Path(project_dir).glob("*.mp4"):
        if f.is_file():
            # scene_001.mp4 형식에서 시퀀스 번호 추출
            name = f.stem
            seq = None
            if name.startswith("scene_") and len(name) >= 9:
                try:
                    seq = int(name.split("_")[1])
                except:
                    pass
            
            videos.append({
                "filename": f.name,
                "path": f"proj_{project_id}/{f.name}",
                "sequence": seq,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
    
    # 시퀀스 번호로 정렬 (없으면 생성 시간 순)
    videos.sort(key=lambda x: (x["sequence"] is None, x["sequence"] or 0, x["created"]))
    
    return {
        "project_id": project_id,
        "videos": videos,
        "count": len(videos)
    }


# ============================================================
# 영상 합치기 API
# ============================================================

class MergeRequest(BaseModel):
    """영상 합치기 요청"""
    video_files: List[str] = Field(..., description="합칠 영상 파일명 목록 (순서대로)")
    output_filename: Optional[str] = Field(None, description="출력 파일명 (없으면 자동 생성)")
    
class MergeResponse(BaseModel):
    """영상 합치기 응답"""
    success: bool
    output_file: str
    total_duration: float = Field(description="총 영상 길이 (초)")
    video_count: int = Field(description="합친 영상 개수")
    message: str


@app.post("/merge", response_model=MergeResponse)
async def merge_videos(request: MergeRequest):
    """
    여러 영상을 순서대로 합쳐서 하나의 영상으로 만들기
    
    예시:
    ```json
    {
        "video_files": ["i2v_20241230_001.mp4", "i2v_20241230_002.mp4", "i2v_20241230_003.mp4"],
        "output_filename": "merged_final.mp4"
    }
    ```
    """
    import subprocess
    
    if len(request.video_files) < 2:
        raise HTTPException(status_code=400, detail="최소 2개 이상의 영상이 필요합니다")
    
    # 파일 존재 확인
    video_paths = []
    for filename in request.video_files:
        filepath = os.path.join(OUTPUT_DIR, filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {filename}")
        video_paths.append(filepath)
    
    # 출력 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = request.output_filename or f"merged_{timestamp}.mp4"
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # FFmpeg concat 리스트 파일 생성
    concat_list_path = os.path.join(OUTPUT_DIR, f"concat_{timestamp}.txt")
    try:
        with open(concat_list_path, "w") as f:
            for vpath in video_paths:
                # FFmpeg concat demuxer 형식
                f.write(f"file '{os.path.abspath(vpath)}'\n")
        
        # FFmpeg로 영상 합치기
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",  # 재인코딩 없이 빠르게 합치기
            output_path
        ]
        
        print(f"[Merge] 영상 합치기 시작: {len(video_paths)}개 영상")
        print(f"[Merge] 명령: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # 코덱이 다른 경우 재인코딩으로 재시도
            print(f"[Merge] copy 실패, 재인코딩 시도...")
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
        
        # 결과 영상 정보 가져오기
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            output_path
        ]
        duration_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        total_duration = float(duration_result.stdout.strip()) if duration_result.returncode == 0 else 0
        
        print(f"[Merge] 완료! 출력: {output_filename}, 길이: {total_duration:.2f}초")
        
        return MergeResponse(
            success=True,
            output_file=output_filename,
            total_duration=round(total_duration, 2),
            video_count=len(video_paths),
            message=f"{len(video_paths)}개 영상을 합쳐서 {total_duration:.1f}초 영상 생성 완료"
        )
        
    finally:
        # 임시 파일 삭제
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


@app.post("/merge/all", response_model=MergeResponse)
async def merge_all_videos(output_filename: Optional[str] = None):
    """
    outputs 폴더의 모든 영상을 생성 시간 순서대로 합치기
    
    사용 예: 생성된 5초 영상 8개를 순서대로 합쳐서 40초 영상 만들기
    """
    # outputs 폴더의 모든 mp4 파일 가져오기
    video_files = []
    for f in Path(OUTPUT_DIR).glob("*.mp4"):
        if f.is_file() and not f.name.startswith("merged_"):
            video_files.append({
                "filename": f.name,
                "created": f.stat().st_ctime
            })
    
    if len(video_files) < 2:
        raise HTTPException(status_code=400, detail=f"합칠 영상이 부족합니다 (현재: {len(video_files)}개)")
    
    # 생성 시간 순 정렬
    video_files.sort(key=lambda x: x["created"])
    filenames = [v["filename"] for v in video_files]
    
    print(f"[Merge All] 합칠 영상 목록 ({len(filenames)}개):")
    for i, name in enumerate(filenames, 1):
        print(f"  {i}. {name}")
    
    # merge 함수 호출
    request = MergeRequest(video_files=filenames, output_filename=output_filename)
    return await merge_videos(request)


@app.post("/merge/project/{project_id}", response_model=MergeResponse)
async def merge_project_videos(project_id: str, output_filename: Optional[str] = None):
    """
    특정 프로젝트의 모든 영상을 시퀀스 순서대로 합치기
    
    - **project_id**: 프로젝트 ID
    - **output_filename**: 출력 파일명 (기본: final.mp4)
    
    FE 사용 예시:
    1. 스토리보드 8개 생성 (각각 project_id="story123", sequence=1~8)
    2. POST /merge/project/story123 호출
    3. 결과: proj_story123/final.mp4 (40초 영상)
    """
    import subprocess
    
    project_dir = os.path.join(OUTPUT_DIR, f"proj_{project_id}")
    
    if not os.path.exists(project_dir):
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    
    # 프로젝트 폴더의 모든 scene 영상 가져오기
    video_files = []
    for f in Path(project_dir).glob("scene_*.mp4"):
        if f.is_file():
            # scene_001.mp4 형식에서 시퀀스 번호 추출
            name = f.stem
            seq = 999999
            try:
                seq = int(name.split("_")[1])
            except:
                pass
            
            video_files.append({
                "path": str(f),
                "filename": f.name,
                "sequence": seq
            })
    
    if len(video_files) < 2:
        raise HTTPException(
            status_code=400, 
            detail=f"합칠 영상이 부족합니다 (현재: {len(video_files)}개). 최소 2개 이상의 scene_XXX.mp4 파일이 필요합니다."
        )
    
    # 시퀀스 순서로 정렬
    video_files.sort(key=lambda x: x["sequence"])
    
    print(f"[Merge Project] 프로젝트 {project_id} 합치기 ({len(video_files)}개 영상):")
    for i, v in enumerate(video_files, 1):
        print(f"  {i}. {v['filename']} (seq: {v['sequence']})")
    
    # 출력 파일명 설정
    final_filename = output_filename or "final.mp4"
    if not final_filename.endswith(".mp4"):
        final_filename += ".mp4"
    output_path = os.path.join(project_dir, final_filename)
    
    # FFmpeg concat 리스트 파일 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    concat_list_path = os.path.join(project_dir, f"concat_{timestamp}.txt")
    
    try:
        with open(concat_list_path, "w") as f:
            for v in video_files:
                f.write(f"file '{v['filename']}'\n")  # 파일명만 작성!
        
        # FFmpeg로 영상 합치기 (프로젝트 폴더 내 상대경로)
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", os.path.basename(concat_list_path),  # 파일명만 전달
            "-c", "copy",
            final_filename
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_dir)
        
        if result.returncode != 0:
            # 재인코딩으로 재시도
            print(f"[Merge Project] copy 실패, 재인코딩 시도...")
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
        
        # 결과 영상 정보
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            output_path
        ]
        duration_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        total_duration = float(duration_result.stdout.strip()) if duration_result.returncode == 0 else 0
        
        relative_path = f"proj_{project_id}/{final_filename}"
        print(f"[Merge Project] 완료! 출력: {relative_path}, 길이: {total_duration:.2f}초")
        
        return MergeResponse(
            success=True,
            output_file=relative_path,
            total_duration=round(total_duration, 2),
            video_count=len(video_files),
            message=f"프로젝트 {project_id}: {len(video_files)}개 영상을 합쳐서 {total_duration:.1f}초 영상 생성 완료"
        )
        
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


@app.delete("/project/{project_id}")
async def delete_project(project_id: str):
    """프로젝트 전체 삭제 (폴더 및 모든 영상)"""
    project_dir = os.path.join(OUTPUT_DIR, f"proj_{project_id}")
    
    if not os.path.exists(project_dir):
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    
    # 폴더 내 파일 개수
    file_count = len(list(Path(project_dir).glob("*")))
    
    # 폴더 삭제
    shutil.rmtree(project_dir)
    
    return {
        "success": True,
        "message": f"프로젝트 {project_id} 삭제 완료 ({file_count}개 파일 삭제됨)"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4200)

