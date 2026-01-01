"""
EXAONE 광고 시나리오 생성 API
LGAI-EXAONE/EXAONE-4.0-1.2B 모델 기반
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import uvicorn

# ============================================
# FastAPI 앱 초기화
# ============================================
app = FastAPI(
    title="EXAONE 광고 시나리오 생성 API",
    description="LGAI-EXAONE 모델 기반 광고 영상 시나리오 자동 생성 API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# 전역 변수 (모델, 토크나이저)
# ============================================
model = None
tokenizer = None
MODEL_NAME = "LGAI-EXAONE/EXAONE-4.0-1.2B"

# ============================================
# 시스템 프롬프트
# ============================================
SYSTEM_PROMPT = """당신은 광고 영상 시나리오를 작성하는 크리에이티브 디렉터입니다.
사용자가 제공한 브랜드 이름과 키워드를 기반으로, 실제 촬영이 가능할 정도로 구체적인 영상 시나리오를 작성하세요.

**시나리오 작성 규칙**

결과물은 6~7문장으로 구성합니다.

반드시 브랜드 이름과 제품명을 자연스럽게 포함합니다.

공간(배경), 인물의 행동, 화면 전환, 제품 사용 장면이 순차적으로 드러나야 합니다.

광고 톤은 감성적이고 깨끗하며 라이프스타일 중심으로 작성합니다.

불필요한 설명이나 메타 발언 없이 시나리오 문장만 출력합니다.

**포함해야 할 요소**

- 실내/야외 배경 묘사
- 인물의 동작 및 표정
- 제품을 집어 드는 장면
- 제품 사용(바르는 장면, 사용 후 느낌 등)
- 화면 전환 또는 컷 변화
- 브랜드 이미지가 느껴지는 마무리"""

DEFAULT_USER_QUERY = "자연스러운 일상 속에서 제품을 사용하는 감성적인 광고 시나리오를 작성해주세요."

# ============================================
# Pydantic 모델 (Request/Response)
# ============================================
class ScenarioRequest(BaseModel):
    brand: str = Field(..., description="브랜드 이름 (예: 이니스프리, 라네즈)")
    user_query: Optional[str] = Field(None, description="시나리오 생성 요청 (선택사항)")
    max_tokens: Optional[int] = Field(256, description="최대 생성 토큰 수")
    temperature: Optional[float] = Field(0.7, description="생성 다양성 (0.0~1.0)")

class ScenarioResponse(BaseModel):
    success: bool
    brand: str
    query: str
    scenario: str
    model: str

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_name: str

class BrandsResponse(BaseModel):
    brands: List[str]

# ============================================
# 모델 로드 함수
# ============================================
def load_model():
    """EXAONE 모델을 로드합니다 (최초 1회만 실행)"""
    global model, tokenizer
    
    if model is not None:
        return  # 이미 로드됨
    
    print(f"모델 로딩 중: {MODEL_NAME}")
    
    try:
        # GPU 사용 가능 여부 확인
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"사용 디바이스: {device}")
        
        # 토크나이저 로드
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        
        # 모델 로드
        if device == "cuda":
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                torch_dtype=torch.float32,
                trust_remote_code=True
            )
            model = model.to(device)
        
        print("모델 로딩 완료!")
        
    except Exception as e:
        print(f"모델 로딩 실패: {str(e)}")
        raise e

# ============================================
# 시나리오 생성 함수
# ============================================
def generate_scenario(
    brand: str,
    user_query: Optional[str] = None,
    max_tokens: int = 256,
    temperature: float = 0.7
) -> str:
    """
    광고 시나리오를 생성합니다.
    
    Args:
        brand: 브랜드 이름
        user_query: 사용자 요청 (없으면 기본값 사용)
        max_tokens: 최대 생성 토큰 수
        temperature: 생성 다양성
    
    Returns:
        생성된 시나리오 텍스트
    """
    global model, tokenizer
    
    # 모델이 로드되지 않았으면 로드
    if model is None:
        load_model()
    
    # 유저 쿼리가 없으면 기본값 사용
    if not user_query or user_query.strip() == "":
        user_query = DEFAULT_USER_QUERY
    
    # 프롬프트 구성
    full_prompt = f"{SYSTEM_PROMPT}\n\n브랜드: {brand}\n\n{user_query}"
    
    messages = [
        {"role": "user", "content": full_prompt}
    ]
    
    # 토큰화
    input_ids = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt"
    )
    
    # 생성
    with torch.no_grad():
        output = model.generate(
            input_ids.to(model.device),
            max_new_tokens=max_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id
        )
    
    # 생성된 부분만 추출
    generated_ids = output[0][input_ids.shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
    
    # 후처리: <think> 태그 제거
    if "<think>" in generated_text:
        parts = generated_text.split("</think>")
        if len(parts) > 1:
            generated_text = parts[1].strip()
    
    return generated_text.strip()

# ============================================
# API 엔드포인트
# ============================================

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 모델 로드"""
    print("서버 시작 - 모델 로딩 시작...")
    try:
        load_model()
        print("서버 준비 완료!")
    except Exception as e:
        print(f"모델 로딩 실패 (요청 시 재시도): {str(e)}")


@app.get("/", tags=["Root"])
async def root():
    """API 루트 - 서버 상태 확인"""
    return {
        "message": "EXAONE 광고 시나리오 생성 API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """서버 및 모델 상태 확인"""
    return HealthResponse(
        status="ok",
        model_loaded=model is not None,
        model_name=MODEL_NAME
    )


@app.get("/brands", response_model=BrandsResponse, tags=["Brands"])
async def get_brands():
    """사용 가능한 브랜드 목록 반환"""
    return BrandsResponse(
        brands=[
            "이니스프리",
            "에뛰드",
            "라네즈",
            "설화수",
            "헤라",
            "아이오페"
        ]
    )


@app.post("/generate", response_model=ScenarioResponse, tags=["Scenario"])
async def create_scenario(request: ScenarioRequest):
    """
    광고 시나리오 생성
    
    - **brand**: 브랜드 이름 (필수)
    - **user_query**: 시나리오 요청 내용 (선택, 기본값 사용 가능)
    - **max_tokens**: 최대 생성 토큰 수 (기본값: 256)
    - **temperature**: 생성 다양성 0.0~1.0 (기본값: 0.7)
    """
    try:
        # 시나리오 생성
        scenario = generate_scenario(
            brand=request.brand,
            user_query=request.user_query,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )
        
        return ScenarioResponse(
            success=True,
            brand=request.brand,
            query=request.user_query if request.user_query else DEFAULT_USER_QUERY,
            scenario=scenario,
            model=MODEL_NAME
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"시나리오 생성 중 오류 발생: {str(e)}"
        )


# ============================================
# 메인 실행
# ============================================
if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=3000,
        reload=False  # 프로덕션에서는 False
    )
