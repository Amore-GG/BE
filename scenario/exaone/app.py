from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from inference_ import generate_scenario, load_model
import uvicorn

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
    """
    try:
        # 시나리오 생성
        scenario = generate_scenario(
            brand=request.brand,
            user_query=request.user_query if request.user_query else None
        )

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
            "아이오페"
        ]
    }

# 헬스 체크
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "서버가 정상 작동 중입니다."}

# 루트 경로 - HTML 페이지 제공
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=3000,
        reload=True
    )
