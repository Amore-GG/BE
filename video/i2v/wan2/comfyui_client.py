"""
ComfyUI API Client for Image-to-Video
ComfyUI 서버와 통신하는 클라이언트 (영상 생성용)
"""

import json
import uuid
import httpx
import websockets
import asyncio
from typing import Optional, Dict, Any
import base64
from pathlib import Path


class ComfyUIClient:
    def __init__(self, server_url: str = "http://localhost:8188"):
        self.server_url = server_url.rstrip("/")
        self.client_id = str(uuid.uuid4())
    
    async def upload_image(self, image_path: str, filename: Optional[str] = None) -> str:
        """이미지를 ComfyUI 서버에 업로드"""
        if filename is None:
            filename = Path(image_path).name
        
        async with httpx.AsyncClient() as client:
            with open(image_path, "rb") as f:
                files = {"image": (filename, f, "image/png")}
                data = {"overwrite": "true"}
                response = await client.post(
                    f"{self.server_url}/upload/image",
                    files=files,
                    data=data
                )
                
                if response.status_code != 200:
                    print(f"[Upload Error] Status: {response.status_code}")
                    print(f"[Upload Error] Response: {response.text}")
                    response.raise_for_status()
                
                result = response.json()
                print(f"[Upload Success] {filename} -> {result}")
                return result.get("name", filename)
    
    async def upload_image_bytes(self, image_bytes: bytes, filename: str) -> str:
        """바이트 데이터로 이미지 업로드"""
        async with httpx.AsyncClient() as client:
            files = {"image": (filename, image_bytes, "image/png")}
            data = {"overwrite": "true"}
            response = await client.post(
                f"{self.server_url}/upload/image",
                files=files,
                data=data
            )
            response.raise_for_status()
            result = response.json()
            return result.get("name", filename)
    
    async def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """워크플로우를 큐에 추가하고 prompt_id 반환"""
        payload = {
            "prompt": workflow,
            "client_id": self.client_id
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.server_url}/prompt",
                json=payload
            )
            
            # 에러 시 상세 내용 출력
            if response.status_code != 200:
                print(f"[ComfyUI Error] Status: {response.status_code}")
                print(f"[ComfyUI Error] Response: {response.text}")
                try:
                    error_json = response.json()
                    print(f"[ComfyUI Error] JSON: {error_json}")
                    if "error" in error_json:
                        raise Exception(f"ComfyUI 에러: {error_json['error']}")
                    if "node_errors" in error_json:
                        raise Exception(f"노드 에러: {error_json['node_errors']}")
                except Exception as e:
                    if "ComfyUI 에러" in str(e) or "노드 에러" in str(e):
                        raise
                response.raise_for_status()
            
            result = response.json()
            print(f"[ComfyUI] Prompt queued: {result.get('prompt_id', 'unknown')}")
            return result["prompt_id"]
    
    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """실행 히스토리 조회"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.server_url}/history/{prompt_id}"
            )
            response.raise_for_status()
            return response.json()
    
    async def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """생성된 이미지 다운로드"""
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.server_url}/view",
                params=params
            )
            response.raise_for_status()
            return response.content
    
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
        """WebSocket으로 완료 대기 (영상 생성은 오래 걸림)"""
        ws_url = self.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?clientId={self.client_id}"
        
        print(f"[WebSocket] Connecting to {ws_url}")
        
        executed_nodes = []  # 실행된 노드 추적
        
        async with websockets.connect(ws_url) as websocket:
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise TimeoutError(f"Timeout waiting for prompt {prompt_id}")
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    
                    # 바이너리 메시지는 스킵 (프리뷰 이미지 등)
                    if isinstance(message, bytes):
                        print(f"[WebSocket] Binary message received ({len(message)} bytes), skipping...")
                        continue
                    
                    # 텍스트 메시지만 JSON 파싱
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError as e:
                        print(f"[WebSocket] JSON decode error: {e}")
                        print(f"[WebSocket] Raw message: {message[:200]}...")
                        continue
                    
                    # 실행 시작 메시지
                    if data.get("type") == "execution_start":
                        print(f"[ComfyUI] Execution started for prompt: {prompt_id}")
                    
                    # 캐시된 노드 정보
                    if data.get("type") == "execution_cached":
                        cached = data.get("data", {}).get("nodes", [])
                        if cached:
                            print(f"[ComfyUI] Cached nodes: {cached}")
                    
                    # 진행 상황 로깅
                    if data.get("type") == "progress":
                        progress = data.get("data", {})
                        value = progress.get("value", 0)
                        max_val = progress.get("max", 1)
                        print(f"Progress: {value}/{max_val} ({(value/max_val*100):.1f}%)")
                    
                    if data.get("type") == "executing":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id:
                            node = exec_data.get("node")
                            if node:
                                executed_nodes.append(node)
                                print(f"Executing node: {node}")
                            if node is None:
                                # 실행 완료
                                print("Execution completed!")
                                print(f"[Summary] Total executed nodes: {len(executed_nodes)}")
                                print(f"[Summary] Executed: {executed_nodes}")
                                
                                # 비디오 관련 노드 실행 여부 확인
                                video_nodes = ['57', '58', '224', '68']
                                missing_nodes = [n for n in video_nodes if n not in executed_nodes]
                                if missing_nodes:
                                    print(f"[WARNING] Video nodes NOT executed: {missing_nodes}")
                                    print(f"[WARNING] 57=KSamplerAdvanced(high), 58=KSamplerAdvanced(low), 224=VAEDecodeTiled, 68=VideoCombine")
                                break
                    
                    elif data.get("type") == "execution_error":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id:
                            print(f"[ERROR] Execution error: {exec_data}")
                            raise Exception(f"Execution error: {exec_data}")
                
                except asyncio.TimeoutError:
                    continue
        
        # 히스토리에서 결과 가져오기
        history = await self.get_history(prompt_id)
        return history.get(prompt_id, {})
    
    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        timeout: int = 1800
    ) -> Dict[str, Any]:
        """워크플로우 실행 및 결과 대기"""
        prompt_id = await self.queue_prompt(workflow)
        print(f"Workflow queued with prompt_id: {prompt_id}")
        result = await self.wait_for_completion(prompt_id, timeout)
        return result
    
    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """JSON 파일에서 워크플로우 로드"""
        with open(workflow_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def update_i2v_workflow(
        self,
        workflow: Dict[str, Any],
        image_filename: str,
        prompt: str,
        width: int = 512,
        height: int = 512,
        length: int = 121,
        steps: int = 8,
        cfg: float = 1.0
    ) -> Dict[str, Any]:
        """Image-to-Video 워크플로우 업데이트"""
        workflow = json.loads(json.dumps(workflow))  # Deep copy
        
        print(f"[Workflow] 업데이트 시작: image={image_filename}, prompt={prompt[:50]}...")
        print(f"[Workflow] 파라미터: width={width}, height={height}, length={length}, steps={steps}, cfg={cfg}")
        
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            title = node.get("_meta", {}).get("title", "")
            inputs = node.get("inputs", {})
            
            # 이미지 로드 노드 (노드 172)
            if class_type == "LoadImage":
                inputs["image"] = image_filename
                print(f"[Workflow] 노드 {node_id} (LoadImage): image={image_filename}")
            
            # Positive Prompt (노드 6)
            elif class_type == "CLIPTextEncode":
                if "Positive" in title:
                    inputs["text"] = prompt
                    print(f"[Workflow] 노드 {node_id} (Positive Prompt): 설정됨")
            
            # 파라미터 노드들 (easy int, easy float)
            elif class_type == "easy int":
                if "Width" in title:
                    inputs["value"] = width
                    print(f"[Workflow] 노드 {node_id} (Width): {width}")
                elif "Height" in title:
                    inputs["value"] = height
                    print(f"[Workflow] 노드 {node_id} (Height): {height}")
                elif "Length" in title:
                    inputs["value"] = length
                    print(f"[Workflow] 노드 {node_id} (Length): {length}")
                elif "Steps" in title:
                    inputs["value"] = steps
                    print(f"[Workflow] 노드 {node_id} (Steps): {steps}")
            
            elif class_type == "easy float":
                if "CFG" in title:
                    inputs["value"] = cfg
                    print(f"[Workflow] 노드 {node_id} (CFG): {cfg}")
        
        return workflow
    
    def update_workflow_images(
        self,
        workflow: Dict[str, Any],
        image1_name: str,
        image2_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """워크플로우의 이미지 파일명 업데이트 (호환성)"""
        workflow = json.loads(json.dumps(workflow))
        
        for node_id, node in workflow.items():
            if node.get("class_type") == "LoadImage":
                inputs = node.get("inputs", {})
                if "image" in inputs:
                    inputs["image"] = image1_name
        
        return workflow
    
    def update_workflow_prompt(
        self,
        workflow: Dict[str, Any],
        prompt: str
    ) -> Dict[str, Any]:
        """워크플로우의 프롬프트 업데이트 (호환성)"""
        workflow = json.loads(json.dumps(workflow))
        
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            
            if class_type == "CLIPTextEncode":
                title = node.get("_meta", {}).get("title", "")
                if "Positive" in title:
                    node["inputs"]["text"] = prompt
        
        return workflow

