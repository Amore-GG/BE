"""
ComfyUI API Client for LatentSync
ComfyUI 서버와 통신하는 클라이언트 (립싱크 생성용)
"""

import json
import uuid
import httpx
import websockets
import asyncio
import random
from typing import Optional, Dict, Any
from pathlib import Path


class ComfyUIClient:
    def __init__(self, server_url: str = "http://localhost:8188"):
        self.server_url = server_url.rstrip("/")
        self.client_id = str(uuid.uuid4())
    
    async def upload_file(
        self, 
        file_path: str, 
        filename: Optional[str] = None,
        file_type: str = "video"  # "video" or "audio"
    ) -> str:
        """파일을 ComfyUI 서버에 업로드"""
        if filename is None:
            filename = Path(file_path).name
        
        # 파일 타입에 따른 MIME 타입 결정
        if file_type == "audio":
            mime_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
            upload_type = "input"
        else:  # video
            mime_type = "video/mp4"
            upload_type = "input"
        
        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                files = {"image": (filename, f, mime_type)}  # ComfyUI는 'image' 필드 사용
                data = {"overwrite": "true", "type": upload_type}
                
                response = await client.post(
                    f"{self.server_url}/upload/image",
                    files=files,
                    data=data
                )
                
                if response.status_code != 200:
                    print(f"[Upload Error] Status: {response.status_code}")
                    print(f"[Upload Error] Response: {response.text}")
                    raise Exception(f"ComfyUI 파일 업로드 실패: {response.text}")
                
                result = response.json()
                print(f"[Upload Success] {filename} -> {result}")
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
            
            if response.status_code != 200:
                print(f"[ComfyUI Error] Status: {response.status_code}")
                print(f"[ComfyUI Error] Response: {response.text}")
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        raise Exception(f"ComfyUI 에러: {error_json['error']}")
                except json.JSONDecodeError:
                    raise Exception(f"ComfyUI 응답 에러: {response.text}")
            
            result = response.json()
            prompt_id = result["prompt_id"]
            print(f"[ComfyUI] Prompt queued: {prompt_id}")
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
        
        print(f"[WebSocket] Connecting to {ws_url}")
        
        async with websockets.connect(ws_url) as websocket:
            print(f"[WebSocket] Connected!")
            start_time = asyncio.get_event_loop().time()
            
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
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
                        print(f"[Progress] {value}/{max_val} ({pct:.1f}%)")
                    
                    elif msg_type == "executing":
                        exec_data = data.get("data", {})
                        recv_prompt_id = exec_data.get("prompt_id")
                        
                        if recv_prompt_id == prompt_id:
                            node = exec_data.get("node")
                            if node:
                                print(f"[Executing] Node {node}")
                            if node is None:
                                print(f"[ComfyUI] Execution COMPLETED!")
                                break
                    
                    elif msg_type == "execution_error":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id:
                            raise Exception(f"Execution error: {exec_data}")
                
                except asyncio.TimeoutError:
                    continue
        
        history = await self.get_history(prompt_id)
        return history.get(prompt_id, {})
    
    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        timeout: int = 1800
    ) -> Dict[str, Any]:
        """워크플로우 실행 및 결과 대기"""
        prompt_id = await self.queue_prompt(workflow)
        result = await self.wait_for_completion(prompt_id, timeout)
        return result
    
    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """JSON 파일에서 워크플로우 로드"""
        with open(workflow_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def update_lipsync_workflow(
        self,
        workflow: Dict[str, Any],
        video_filename: str,
        audio_filename: str,
        seed: Optional[int] = None,
        lips_expression: float = 1.5,
        inference_steps: int = 20,
        fps: int = 25
    ) -> Dict[str, Any]:
        """LatentSync 워크플로우 업데이트"""
        workflow = json.loads(json.dumps(workflow))  # Deep copy
        
        if seed is None:
            seed = random.randint(0, 2**31 - 1)
        
        print(f"[Workflow] 업데이트 시작:")
        print(f"  - video: {video_filename}")
        print(f"  - audio: {audio_filename}")
        print(f"  - seed: {seed}")
        print(f"  - lips_expression: {lips_expression}")
        print(f"  - inference_steps: {inference_steps}")
        print(f"  - fps: {fps}")
        
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})
            
            # LoadAudio 노드 (노드 37)
            if class_type == "LoadAudio":
                inputs["audio"] = audio_filename
                print(f"[Workflow] 노드 {node_id} (LoadAudio): {audio_filename}")
            
            # VHS_LoadVideo 노드 (노드 40)
            elif class_type == "VHS_LoadVideo":
                inputs["video"] = video_filename
                inputs["force_rate"] = fps
                print(f"[Workflow] 노드 {node_id} (VHS_LoadVideo): {video_filename}, fps={fps}")
            
            # LatentSyncNode 노드 (노드 54)
            elif class_type == "LatentSyncNode":
                inputs["seed"] = seed
                inputs["lips_expression"] = lips_expression
                inputs["inference_steps"] = inference_steps
                print(f"[Workflow] 노드 {node_id} (LatentSyncNode): seed={seed}, lips={lips_expression}, steps={inference_steps}")
            
            # VideoLengthAdjuster 노드 (노드 55)
            elif class_type == "VideoLengthAdjuster":
                inputs["fps"] = fps
                print(f"[Workflow] 노드 {node_id} (VideoLengthAdjuster): fps={fps}")
            
            # VHS_VideoCombine 노드 (노드 41)
            elif class_type == "VHS_VideoCombine":
                inputs["frame_rate"] = fps
                print(f"[Workflow] 노드 {node_id} (VHS_VideoCombine): frame_rate={fps}")
        
        return workflow

