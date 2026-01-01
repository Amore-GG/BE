"""
ComfyUI API Client for MMAudio
ComfyUI 서버와 통신하는 클라이언트 (오디오 생성용)
"""

import json
import uuid
import httpx
import websockets
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path


def log(message: str, level: str = "INFO"):
    """타임스탬프가 포함된 로그 출력"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


class ComfyUIClient:
    def __init__(self, server_url: str = "http://localhost:8188"):
        self.server_url = server_url.rstrip("/")
        self.client_id = str(uuid.uuid4())
        
        # 노드 이름 매핑
        self.node_names = {
            "VHS_LoadVideo": "비디오 로드",
            "VHS_VideoInfo": "비디오 정보 추출",
            "MMAudioModelLoader": "MMAudio 모델 로드",
            "MMAudioFeatureUtilsLoader": "MMAudio 특성 로더",
            "MMAudioSampler": "오디오 생성 (샘플링)",
            "VHS_VideoCombine": "비디오+오디오 합성",
            "PreviewAudio": "오디오 미리보기"
        }
    
    async def upload_file(
        self, 
        file_path: str, 
        filename: Optional[str] = None,
        file_type: str = "video"
    ) -> str:
        """파일을 ComfyUI 서버에 업로드"""
        if filename is None:
            filename = Path(file_path).name
        
        file_size = Path(file_path).stat().st_size / (1024 * 1024)  # MB
        log(f"파일 업로드 시작: {filename} ({file_size:.2f}MB)")
        
        mime_type = "video/mp4"
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(file_path, "rb") as f:
                files = {"image": (filename, f, mime_type)}
                data = {"overwrite": "true", "type": "input"}
                
                response = await client.post(
                    f"{self.server_url}/upload/image",
                    files=files,
                    data=data
                )
                
                elapsed = time.time() - start_time
                
                if response.status_code != 200:
                    log(f"업로드 실패: {response.status_code} - {response.text}", "ERROR")
                    raise Exception(f"ComfyUI 파일 업로드 실패: {response.text}")
                
                result = response.json()
                log(f"업로드 완료: {filename} ({elapsed:.1f}초)", "SUCCESS")
                return result.get("name", filename)
    
    async def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """워크플로우를 큐에 추가하고 prompt_id 반환"""
        log("워크플로우 큐에 추가 중...")
        
        payload = {
            "prompt": workflow,
            "client_id": self.client_id
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.server_url}/prompt",
                json=payload
            )
            
            if response.status_code != 200:
                log(f"큐 추가 실패: {response.status_code}", "ERROR")
                log(f"응답: {response.text}", "ERROR")
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        raise Exception(f"ComfyUI 에러: {error_json['error']}")
                except json.JSONDecodeError:
                    raise Exception(f"ComfyUI 응답 에러: {response.text}")
            
            result = response.json()
            prompt_id = result["prompt_id"]
            log(f"워크플로우 큐 추가됨: {prompt_id[:8]}...")
            return prompt_id
    
    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """실행 히스토리 조회"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.server_url}/history/{prompt_id}"
            )
            response.raise_for_status()
            return response.json()
    
    async def get_video(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """생성된 비디오 다운로드"""
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.get(
                f"{self.server_url}/view",
                params=params
            )
            response.raise_for_status()
            return response.content
    
    async def wait_for_completion(self, prompt_id: str, timeout: int = 1800) -> Dict[str, Any]:
        """WebSocket으로 완료 대기"""
        ws_url = self.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?clientId={self.client_id}"
        
        log("ComfyUI WebSocket 연결 중...")
        
        async with websockets.connect(ws_url) as websocket:
            log("WebSocket 연결됨 - 오디오 생성 대기 중...")
            start_time = asyncio.get_event_loop().time()
            last_progress_log = 0
            current_node = None
            
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    log(f"타임아웃! ({timeout}초 초과)", "ERROR")
                    raise TimeoutError(f"Timeout waiting for prompt {prompt_id}")
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    
                    if isinstance(message, bytes):
                        continue
                    
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    
                    msg_type = data.get("type", "unknown")
                    
                    if msg_type == "progress":
                        progress = data.get("data", {})
                        value = progress.get("value", 0)
                        max_val = progress.get("max", 1)
                        pct = (value/max_val*100) if max_val > 0 else 0
                        
                        # 10% 단위로만 로그 출력 (스팸 방지)
                        if pct - last_progress_log >= 10 or pct >= 100:
                            node_name = self.node_names.get(current_node, current_node or "처리 중")
                            log(f"[{node_name}] 진행률: {pct:.0f}% ({value}/{max_val})")
                            last_progress_log = pct
                    
                    elif msg_type == "executing":
                        exec_data = data.get("data", {})
                        recv_prompt_id = exec_data.get("prompt_id")
                        
                        if recv_prompt_id == prompt_id:
                            node = exec_data.get("node")
                            if node:
                                current_node = self._get_node_class(node)
                                node_name = self.node_names.get(current_node, current_node)
                                elapsed_min = elapsed / 60
                                log(f"실행 중: {node_name} (노드 {node}) [{elapsed_min:.1f}분 경과]")
                                last_progress_log = 0  # 노드 변경시 진행률 리셋
                            if node is None:
                                total_time = time.time() - start_time
                                log(f"오디오 생성 완료! (총 {total_time:.1f}초)", "SUCCESS")
                                break
                    
                    elif msg_type == "execution_error":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id:
                            log(f"실행 오류: {exec_data}", "ERROR")
                            raise Exception(f"Execution error: {exec_data}")
                
                except asyncio.TimeoutError:
                    # 5초마다 대기 중 표시
                    elapsed_min = elapsed / 60
                    if int(elapsed) % 30 == 0:
                        log(f"처리 대기 중... ({elapsed_min:.1f}분 경과)")
                    continue
        
        history = await self.get_history(prompt_id)
        return history.get(prompt_id, {})
    
    def _get_node_class(self, node_id: str) -> str:
        """노드 ID에서 클래스 타입 추출 (워크플로우에서)"""
        # 이 메서드는 실행 중 워크플로우 정보가 없으므로 노드 ID만 반환
        return node_id
    
    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        timeout: int = 1800
    ) -> Dict[str, Any]:
        """워크플로우 실행 및 결과 대기"""
        log("=" * 50)
        log("MMAudio 오디오 생성 시작")
        log("=" * 50)
        
        start_time = time.time()
        prompt_id = await self.queue_prompt(workflow)
        result = await self.wait_for_completion(prompt_id, timeout)
        
        total_time = time.time() - start_time
        log(f"워크플로우 총 실행 시간: {total_time:.1f}초 ({total_time/60:.1f}분)", "SUCCESS")
        log("=" * 50)
        
        return result
    
    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """JSON 파일에서 워크플로우 로드"""
        log(f"워크플로우 로드: {workflow_path}")
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        log(f"워크플로우 노드 수: {len(workflow)}개")
        return workflow
    
    def update_mmaudio_workflow(
        self,
        workflow: Dict[str, Any],
        video_filename: str,
        force_rate: int = 24
    ) -> Dict[str, Any]:
        """MMAudio 워크플로우 업데이트"""
        workflow = json.loads(json.dumps(workflow))  # Deep copy
        
        log("-" * 40)
        log("워크플로우 설정:")
        log(f"  - 입력 비디오: {video_filename}")
        log(f"  - 프레임레이트: {force_rate}fps")
        log("-" * 40)
        
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})
            
            # VHS_LoadVideo 노드 (노드 91)
            if class_type == "VHS_LoadVideo":
                inputs["video"] = video_filename
                inputs["force_rate"] = force_rate
                log(f"노드 {node_id} (비디오 로드): {video_filename}")
            
            # MMAudioSampler 노드 - 샘플링 설정 로그
            elif class_type == "MMAudioSampler":
                steps = inputs.get("steps", "?")
                cfg = inputs.get("cfg", "?")
                seed = inputs.get("seed", "?")
                prompt = inputs.get("prompt", "")[:30] + "..."
                log(f"노드 {node_id} (오디오 생성): steps={steps}, cfg={cfg}, seed={seed}")
                log(f"  프롬프트: {prompt}")
            
            # VHS_VideoCombine 노드 (노드 97)
            elif class_type == "VHS_VideoCombine":
                format_type = inputs.get("format", "?")
                log(f"노드 {node_id} (비디오 합성): 포맷={format_type}")
        
        return workflow

