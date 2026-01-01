from transformers import AutoModelForCausalLM, AutoTokenizer

# 시스템 프롬프트 (plan.md 기반)
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

# 디폴트 유저 쿼리
DEFAULT_USER_QUERY = "자연스러운 일상 속에서 제품을 사용하는 감성적인 광고 시나리오를 작성해주세요."

# 모델 초기화 (전역으로 로드)
model_name = "LGAI-EXAONE/EXAONE-4.0-1.2B"
model = None
tokenizer = None

def load_model():
    """모델을 로드합니다 (최초 1회만 실행)"""
    global model, tokenizer
    if model is None:
        print("모델 로딩 중...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype="bfloat16",
            device_map="auto"
        )
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        print("모델 로딩 완료!")

def generate_scenario(brand: str, user_query: str = None) -> str:
    """
    광고 시나리오를 생성합니다.

    Args:
        brand: 브랜드 이름 (예: "이니스프리", "에뛰드", "라네즈")
        user_query: 사용자 입력 쿼리 (None이면 디폴트 사용)

    Returns:
        생성된 시나리오 텍스트
    """
    load_model()

    # 유저 쿼리가 없으면 디폴트 사용
    if not user_query or user_query.strip() == "":
        user_query = DEFAULT_USER_QUERY

    # 최종 프롬프트 구성: 시스템 프롬프트 + 브랜드 + 유저 쿼리
    full_prompt = f"{SYSTEM_PROMPT}\n\n브랜드: {brand}\n\n{user_query}"

    messages = [
        {"role": "user", "content": full_prompt}
    ]

    input_ids = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt"
    )

    output = model.generate(
        input_ids.to(model.device),
        max_new_tokens=256,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
    )

    # 입력 프롬프트 제거 - 실제 생성된 부분만 추출
    # input_ids의 길이만큼을 제외하고 새로 생성된 토큰만 디코딩
    generated_ids = output[0][input_ids.shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # 추가 정제: <think> 태그나 불필요한 부분 제거
    if "<think>" in generated_text:
        # <think> 태그 이후 부분 추출
        parts = generated_text.split("</think>")
        if len(parts) > 1:
            generated_text = parts[1].strip()

    return generated_text.strip()

# 테스트 실행
if __name__ == "__main__":
    test_brand = "이니스프리"
    test_query = ""  # 디폴트 사용

    print(f"브랜드: {test_brand}")
    print(f"쿼리: {test_query if test_query else '(디폴트)'}")
    print("\n생성 중...\n")

    result = generate_scenario(test_brand, test_query)
    print("=" * 50)
    print(result)
    print("=" * 50)