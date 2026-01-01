"""
ComfyUI 클라이언트
Z-Image Turbo 워크플로우용
"""

import json
import uuid
import asyncio
from typing import Optional, Dict, Any
import httpx
import websockets


class ComfyUIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.client_id = str(uuid.uuid4())
    
    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """워크플로우 JSON 파일 로드"""
        with open(workflow_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def update_image_workflow(
        self,
        workflow: Dict[str, Any],
        prompt: str,
        negative_prompt: str = "blurry ugly bad",
        width: int = 1024,
        height: int = 1024,
        steps: int = 9,
        cfg: float = 1.0,
        seed: int = None
    ) -> Dict[str, Any]:
        """
        Z-Image Turbo 워크플로우 업데이트
        """
        print(f"[Workflow] 업데이트 시작:")
        print(f"  - prompt: {prompt[:50]}...")
        print(f"  - negative: {negative_prompt[:30]}...")
        print(f"  - size: {width}x{height}")
        print(f"  - steps: {steps}, cfg: {cfg}, seed: {seed}")
        
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            
            # Positive Prompt (노드 6)
            if class_type == "CLIPTextEncode" and "Positive" in node.get("_meta", {}).get("title", ""):
                node["inputs"]["text"] = prompt
                print(f"[Workflow] 노드 {node_id} (Positive Prompt): 업데이트됨")
            
            # Negative Prompt (노드 7)
            if class_type == "CLIPTextEncode" and "Negative" in node.get("_meta", {}).get("title", ""):
                node["inputs"]["text"] = negative_prompt
                print(f"[Workflow] 노드 {node_id} (Negative Prompt): 업데이트됨")
            
            # EmptySD3LatentImage (노드 13) - 이미지 크기
            if class_type == "EmptySD3LatentImage":
                node["inputs"]["width"] = width
                node["inputs"]["height"] = height
                print(f"[Workflow] 노드 {node_id} (LatentImage): {width}x{height}")
            
            # KSampler (노드 3)
            if class_type == "KSampler":
                node["inputs"]["steps"] = steps
                node["inputs"]["cfg"] = cfg
                if seed is not None:
                    node["inputs"]["seed"] = seed
                print(f"[Workflow] 노드 {node_id} (KSampler): steps={steps}, cfg={cfg}, seed={seed}")
        
        return workflow
    
    async def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """워크플로우를 ComfyUI 큐에 추가"""
        payload = {
            "prompt": workflow,
            "client_id": self.client_id
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json=payload
            )
            
            if response.status_code != 200:
                error_text = response.text
                try:
                    error_json = response.json()
                    print(f"[ComfyUI Error] Status: {response.status_code}")
                    print(f"[ComfyUI Error] Response: {error_text}")
                    raise Exception(f"ComfyUI 에러: {error_json['error']}")
                except json.JSONDecodeError:
                    raise Exception(f"ComfyUI 요청 실패 ({response.status_code}): {error_text}")
            
            result = response.json()
            return result["prompt_id"]
    
    async def wait_for_completion(self, prompt_id: str, timeout: float = 300) -> Dict[str, Any]:
        """워크플로우 완료 대기 (WebSocket)"""
        ws_url = f"{self.ws_url}/ws?clientId={self.client_id}"
        
        try:
            async with websockets.connect(ws_url) as ws:
                start_time = asyncio.get_event_loop().time()
                
                while True:
                    if asyncio.get_event_loop().time() - start_time > timeout:
                        raise TimeoutError(f"워크플로우 타임아웃 ({timeout}초)")
                    
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(message)
                        
                        if data.get("type") == "executing":
                            exec_data = data.get("data", {})
                            if exec_data.get("prompt_id") == prompt_id:
                                node = exec_data.get("node")
                                if node is None:
                                    print(f"[ComfyUI] 워크플로우 완료: {prompt_id}")
                                    break
                                else:
                                    print(f"[ComfyUI] 실행 중: 노드 {node}")
                        
                        elif data.get("type") == "execution_error":
                            error_data = data.get("data", {})
                            if error_data.get("prompt_id") == prompt_id:
                                raise Exception(f"실행 오류: {error_data}")
                    
                    except asyncio.TimeoutError:
                        continue
        
        except Exception as e:
            if "websockets" in str(type(e).__module__):
                print(f"[ComfyUI] WebSocket 연결 실패, 폴링으로 전환...")
                return await self._poll_for_completion(prompt_id, timeout)
            raise
        
        return await self.get_history(prompt_id)
    
    async def _poll_for_completion(self, prompt_id: str, timeout: float = 300) -> Dict[str, Any]:
        """폴링으로 완료 대기"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise TimeoutError(f"워크플로우 타임아웃 ({timeout}초)")
            
            history = await self.get_history(prompt_id)
            if history and "outputs" in history:
                return history
            
            await asyncio.sleep(1.0)
    
    async def get_history(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """프롬프트 히스토리 조회"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/history/{prompt_id}")
            
            if response.status_code != 200:
                return None
            
            history = response.json()
            if prompt_id in history:
                return history[prompt_id]
            return None
    
    async def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """ComfyUI에서 이미지 다운로드"""
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self.base_url}/view",
                params=params
            )
            
            if response.status_code != 200:
                raise Exception(f"이미지 다운로드 실패: {response.status_code}")
            
            return response.content
    
    async def execute_workflow(self, workflow: Dict[str, Any], timeout: float = 300) -> Dict[str, Any]:
        """워크플로우 실행 및 완료 대기"""
        prompt_id = await self.queue_prompt(workflow)
        print(f"[ComfyUI] 워크플로우 큐 추가됨: {prompt_id}")
        
        result = await self.wait_for_completion(prompt_id, timeout)
        return result

