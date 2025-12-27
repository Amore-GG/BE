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
                response.raise_for_status()
                result = response.json()
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
        
        async with websockets.connect(ws_url) as websocket:
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise TimeoutError(f"Timeout waiting for prompt {prompt_id}")
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data.get("type") == "executing":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id:
                            if exec_data.get("node") is None:
                                # 실행 완료
                                break
                    
                    elif data.get("type") == "execution_error":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id:
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
        workflow = workflow.copy()
        
        # LoadImage 노드 찾아서 업데이트
        for node_id, node in workflow.items():
            if node.get("class_type") == "LoadImage":
                inputs = node.get("inputs", {})
                title = node.get("_meta", {}).get("title", "")
                
                # 첫 번째 이미지
                if "image" in inputs:
                    if image2_name is None:
                        inputs["image"] = image1_name
                    else:
                        # 순서대로 할당 (첫 번째 발견 = image1)
                        if not hasattr(self, "_image_assigned"):
                            self._image_assigned = False
                        
                        if not self._image_assigned:
                            inputs["image"] = image1_name
                            self._image_assigned = True
                        else:
                            inputs["image"] = image2_name
        
        # 임시 변수 정리
        if hasattr(self, "_image_assigned"):
            delattr(self, "_image_assigned")
        
        return workflow
    
    def update_workflow_prompt(
        self,
        workflow: Dict[str, Any],
        prompt: str
    ) -> Dict[str, Any]:
        """워크플로우의 프롬프트 업데이트"""
        workflow = workflow.copy()
        
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

