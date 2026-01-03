from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Dict
from inference_ import generate_scenario, load_model
from timetable_generator import generate_timetable
from streaming_timetable import generate_timetable_streaming
from scenario_validator import validate_scenario_with_retry
from prompt_generator import generate_dialogue_only
import uvicorn
import os
import json

app = FastAPI(title="광고 시나리오 생성기")

# CORS 설정 (프론트엔드와 통신을 위해)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 요청 모델 정의
class ScenarioRequest(BaseModel):
    brand: str
    user_query: str = ""

# 응답 모델 정의
class ScenarioResponse(BaseModel):
    scenario: str
    brand: str
    query: str

# 타임테이블 요청 모델
class TimetableRequest(BaseModel):
    scenario: str
    video_duration: int  # 초 단위
    brand: str = ""  # 선택적

# 타임테이블 응답 모델
class T2IPrompt(BaseModel):
    background: str
    character_pose_and_gaze: str
    product: str
    camera_angle: str

class ImageEditPrompt(BaseModel):
    pose_change: str
    gaze_change: str
    expression: str
    additional_edits: str

class TimeSlot(BaseModel):
    time_start: float
    time_end: float
    scene_description: str
    dialogue: str  # 지지의 발화 내용 (선택적, 빈 문자열 가능)
    background_sounds_prompt: str  # 배경 사운드 프롬프트 (영어, 선택적)
    t2i_prompt: T2IPrompt
    image_edit_prompt: ImageEditPrompt


# 서버 시작시 모델 로드
@app.on_event("startup")
async def startup_event():
    print("서버 시작 - 모델 로딩 중...")
    load_model()
    print("모델 로딩 완료 - 서버 준비됨!")

# 시나리오 생성 API
@app.post("/generate", response_model=ScenarioResponse)
async def create_scenario(request: ScenarioRequest):
    """
    브랜드와 유저 쿼리를 받아 광고 시나리오를 생성합니다.
    문법 및 띄어쓰기 검증을 포함합니다.
    """
    try:
        # 시나리오 생성 함수를 래핑
        def generate_fn(brand, user_query):
            return generate_scenario(brand=brand, user_query=user_query)

        # 시나리오 생성 with 문법/띄어쓰기 검증 (최대 3번 재시도)
        scenario, attempts, validation_history = validate_scenario_with_retry(
            generate_func=generate_fn,
            max_retries=3,
            threshold=7.0,
            brand=request.brand,
            user_query=request.user_query if request.user_query else None
        )

        print(f"시나리오 생성 완료 ({attempts}번 시도)")

        return ScenarioResponse(
            scenario=scenario,
            brand=request.brand,
            query=request.user_query if request.user_query else "디폴트 쿼리 사용"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시나리오 생성 중 오류 발생: {str(e)}")

# 브랜드 목록 API
@app.get("/brands")
async def get_brands():
    """
    사용 가능한 브랜드 목록을 반환합니다.
    """
    return {
        "brands": [
            "이니스프리",
            "에뛰드",
            "라네즈",
            "설화수",
            "헤라",
        ]
    }

# 타임테이블 스트리밍 생성 API (Phase 2) - 개선된 방식
@app.post("/generate-timetable-stream")
async def create_timetable_stream(request: TimetableRequest):
    """
    시나리오를 분석하여 타임테이블을 스트리밍 방식으로 생성합니다.

    - 장면을 하나씩 생성하여 즉시 전송
    - 타임아웃 방지 및 사용자 경험 개선
    """
    async def event_generator():
        try:
            for event in generate_timetable_streaming(
                scenario=request.scenario,
                video_duration=request.video_duration,
                brand=request.brand
            ):
                # SSE 형식으로 전송
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            error_event = {
                "type": "error",
                "data": {"message": str(e)}
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

# 장면 편집 요청 모델
class SceneEditRequest(BaseModel):
    scene_index: int
    dialogue: str = None
    background_sounds_prompt: str = None
    t2i_prompt: T2IPrompt = None
    image_edit_prompt: ImageEditPrompt = None

# 발화 재생성 요청 모델
class DialogueRegenerateRequest(BaseModel):
    scene_description: str
    previous_dialogues: List[str] = []

# 발화 재생성 API
@app.post("/regenerate-dialogue")
async def regenerate_dialogue(request: DialogueRegenerateRequest):
    """
    특정 장면의 발화만 재생성합니다.

    Args:
        scene_description: 장면 설명
        previous_dialogues: 이전 장면들의 발화 리스트 (단어 반복 방지용)

    Returns:
        새로 생성된 발화
    """
    try:
        # 발화 생성
        new_dialogue = generate_dialogue_only(
            korean_scene=request.scene_description,
            previous_dialogues=request.previous_dialogues
        )

        return {
            "status": "success",
            "dialogue": new_dialogue
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"발화 생성 중 오류 발생: {str(e)}")

# 장면 편집 API
@app.patch("/edit-scene")
async def edit_scene(request: SceneEditRequest):
    """
    생성된 장면의 발화, 효과음, T2I 프롬프트, Image Edit 프롬프트를 수정합니다.

    Args:
        scene_index: 수정할 장면의 인덱스
        dialogue: 수정할 발화 (선택)
        sound_effect: 수정할 효과음 (선택)
        t2i_prompt: 수정할 T2I 프롬프트 (선택)
        image_edit_prompt: 수정할 Image Edit 프롬프트 (선택)

    Returns:
        수정 완료 메시지
    """
    try:
        # 실제 구현에서는 세션 기반으로 타임테이블을 저장하고 수정해야 함
        # 현재는 수정 요청을 받았다는 확인만 반환
        updates = {}
        if request.dialogue is not None:
            updates["dialogue"] = request.dialogue
        if request.sound_effect is not None:
            updates["sound_effect"] = request.sound_effect
        if request.t2i_prompt is not None:
            updates["t2i_prompt"] = request.t2i_prompt.dict()
        if request.image_edit_prompt is not None:
            updates["image_edit_prompt"] = request.image_edit_prompt.dict()

        return {
            "status": "success",
            "message": f"Scene {request.scene_index} updated successfully",
            "updates": updates
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"장면 수정 중 오류 발생: {str(e)}")

# 헬스 체크
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "서버가 정상 작동 중입니다."}

# 루트 경로 - HTML 페이지 제공 (Page 1)
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# Page 2 - 타임테이블 생성 페이지
@app.get("/page2", response_class=HTMLResponse)
async def read_page2():
    with open("page2.html", "r", encoding="utf-8") as f:
        return f.read()

# 이미지 파일 서빙
app.mount("/images", StaticFiles(directory="images"), name="images")

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
