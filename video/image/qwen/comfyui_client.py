"""
ComfyUI API Client
ComfyUI 서버와 통신하는 클라이언트
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
                    raise Exception(f"ComfyUI 이미지 업로드 실패 (Status {response.status_code}): {response.text}")
                
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
                    # ComfyUI 에러 메시지 추출
                    if "error" in error_json:
                        raise Exception(f"ComfyUI 에러: {error_json['error']}")
                    if "node_errors" in error_json:
                        raise Exception(f"노드 에러: {error_json['node_errors']}")
                except json.JSONDecodeError:
                    raise Exception(f"ComfyUI 응답 에러 (Status {response.status_code}): {response.text}")
                except Exception as e:
                    if "ComfyUI 에러" in str(e) or "노드 에러" in str(e):
                        raise
                    raise Exception(f"ComfyUI 에러 (Status {response.status_code}): {response.text}")
                response.raise_for_status()
            
            result = response.json()
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
    
    async def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> Dict[str, Any]:
        """WebSocket으로 완료 대기"""
        ws_url = self.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?clientId={self.client_id}"
        
        print(f"[WebSocket] Connecting to {ws_url}")
        
        async with websockets.connect(ws_url) as websocket:
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise TimeoutError(f"Timeout waiting for prompt {prompt_id}")
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    
                    # 바이너리 메시지는 스킵 (프리뷰 이미지 등)
                    if isinstance(message, bytes):
                        print(f"[WebSocket] Binary message received ({len(message)} bytes), skipping...")
                        continue
                    
                    # 텍스트 메시지만 JSON 파싱
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError as e:
                        print(f"[WebSocket] JSON decode error: {e}")
                        continue
                    
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
                                print(f"Executing node: {node}")
                            if node is None:
                                # 실행 완료
                                print("Execution completed!")
                                break
                    
                    elif data.get("type") == "execution_error":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id:
                            print(f"[WebSocket] Execution error: {exec_data}")
                            raise Exception(f"Execution error: {exec_data}")
                
                except asyncio.TimeoutError:
                    continue
        
        # 히스토리에서 결과 가져오기
        history = await self.get_history(prompt_id)
        return history.get(prompt_id, {})
    
    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """워크플로우 실행 및 결과 대기"""
        prompt_id = await self.queue_prompt(workflow)
        result = await self.wait_for_completion(prompt_id, timeout)
        return result
    
    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """JSON 파일에서 워크플로우 로드"""
        with open(workflow_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def update_workflow_images(
        self,
        workflow: Dict[str, Any],
        image1_name: str,
        image2_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """워크플로우의 이미지 파일명 업데이트"""
        import copy
        workflow = copy.deepcopy(workflow)  # Deep copy로 변경
        
        # LoadImage 노드 찾기
        load_image_nodes = []
        for node_id, node in workflow.items():
            if node.get("class_type") == "LoadImage":
                load_image_nodes.append((node_id, node))
        
        # 노드 ID 순으로 정렬 (숫자로 정렬)
        load_image_nodes.sort(key=lambda x: int(x[0]) if x[0].isdigit() else float('inf'))
        
        print(f"[Workflow] LoadImage 노드 발견: {[n[0] for n in load_image_nodes]}")
        
        # 첫 번째 이미지 노드에 image1 할당
        if len(load_image_nodes) >= 1:
            node_id, node = load_image_nodes[0]
            node["inputs"]["image"] = image1_name
            print(f"[Workflow] 노드 {node_id}에 image1 설정: {image1_name}")
        
        # 두 번째 이미지 노드에 image2 할당 (있는 경우)
        if len(load_image_nodes) >= 2 and image2_name:
            node_id, node = load_image_nodes[1]
            node["inputs"]["image"] = image2_name
            print(f"[Workflow] 노드 {node_id}에 image2 설정: {image2_name}")
        
        return workflow
    
    def update_workflow_prompt(
        self,
        workflow: Dict[str, Any],
        prompt: str
    ) -> Dict[str, Any]:
        """워크플로우의 프롬프트 업데이트"""
        import copy
        workflow = copy.deepcopy(workflow)  # Deep copy
        
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            
            # Qwen Image Edit 프롬프트 노드
            if "TextEncodeQwenImageEditPlus" in class_type:
                inputs = node.get("inputs", {})
                if inputs.get("prompt", "") != "":  # Positive 프롬프트만
                    inputs["prompt"] = prompt
            
            # 일반 CLIP 텍스트 인코더 (Positive)
            elif class_type == "CLIPTextEncode":
                title = node.get("_meta", {}).get("title", "")
                if "Positive" in title:
                    node["inputs"]["text"] = prompt
        
        return workflow

