from transformers import AutoModelForCausalLM, AutoTokenizer

# 시스템 프롬프트 (plan.md 기반)
SYSTEM_PROMPT = """당신은 가상 인플루언서 지지(Gigi)의 화장품 광고 영상 시나리오를 작성하는 크리에이티브 디렉터입니다.

**주인공 정보**
- 이름: 지지 (Gigi)
- 성별: 여성
- 설명: 20대 한국 여성 가상 인플루언서, 자연스러운 아름다움, 캐주얼한 라이프스타일

**CRITICAL - 솔로 영상 규칙 (절대 준수)**
- 이것은 지지 혼자만 등장하는 솔로 모노로그 영상입니다
- 지지(여성)만이 모든 장면에 등장해야 합니다
- 절대로 다른 사람이 나오면 안 됩니다 - 가족, 연인, 친구, 낯선 사람, 배경 엑스트라 모두 금지
- 모든 장면은 지지 혼자서 자신의 일상 루틴을 하는 모습을 보여줍니다
- 다른 사람에 대한 언급도 절대 금지 - 엄마, 남자친구, 친구 등

**시나리오 작성 규칙**

결과물은 6~7문장으로 구성합니다.

반드시 브랜드 이름과 제품명을 자연스럽게 포함합니다.

공간(배경), 지지의 행동, 화면 전환, 제품 사용 장면이 순차적으로 드러나야 합니다.

광고 톤은 감성적이고 깨끗하며 라이프스타일 중심으로 작성합니다.

불필요한 설명이나 메타 발언 없이 시나리오 문장만 출력합니다.

**포함해야 할 요소**

- 실내/야외 배경 묘사

- 지지의 동작 및 표정 (혼자만 등장)

- 화장품 제품을 집어 드는 장면

- 제품 사용(바르는 장면, 사용 후 느낌 등)

- 화면 전환 또는 컷 변화

- 브랜드 이미지가 느껴지는 마무리

**사용자 요청사항**
{user_request}"""

# 브랜드별 디폴트 시나리오 요청 (사용자가 입력 안 했을 때 사용)
DEFAULT_SCENARIO_REQUESTS = {
    "이니스프리": "관엽식물이 있는 화이트 + 그린+ 우드 컬러의 실내 집 배경, 지지가 침대에 앉아 침대 앞에 있는 협탁에 손을 뻗어 이니스프리의 '그린티 밀크 보습 에센스'를 손에 쥠, 화면 전환이 되고 세안 밴드를 낀 지지가 민낯 상태로 해당 제품을 바름.",
    "에뛰드": "지지가 전신거울 앞에서 오늘 입은 옷을 체크하는 것으로 시작, 거울 앞에 다가가 에뛰드의 '포근 픽싱 틴트'를 바름, 이후 만족한 듯 웃으며 방을 가방을 걸치고 나가는 장면, 핸드백 안에 틴트를 넣음. 유럽 시가지 배경에서 지지가 걸어가는 옆모습 전신.",
    "라네즈": "지지가 하얀 배경의 스튜디오 OR 집에서 핸드폰으로 민낯 셀카를 찍는 장면을 핸드폰 시점(카메라 프레임) 시점 -> 지지가 사진을 찍는 모습을 관찰자 시점에서 비춤. -> 지지가 하늘색 파자마를 입고 워터 슬리핑 마스크를 팩브러시로 바르는 모습을 정면에서 비춤.",
    "설화수": "설화수의 프리미엄 한방 화장품을 사용하는 지지의 저녁 스킨케어 루틴. 고급스럽고 차분한 분위기로 제품의 영양감과 피부 개선 효과를 강조.",
    "헤라": "헤라의 메이크업 제품으로 준비하는 지지의 외출 전 루틴. 세련되고 트렌디한 분위기로 제품의 발색과 지속력을 강조.",
    "default": "자연스러운 일상 속에서 화장품 제품을 사용하는 지지의 모습. 친근하고 편안한 분위기로 제품의 실용성과 효과를 강조."
}

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
        user_query: 사용자 입력 쿼리 (None이면 브랜드별 디폴트 사용)

    Returns:
        생성된 시나리오 텍스트
    """
    load_model()

    # 유저 쿼리가 없으면 브랜드별 디폴트 사용
    if not user_query or user_query.strip() == "":
        user_request = DEFAULT_SCENARIO_REQUESTS.get(brand, DEFAULT_SCENARIO_REQUESTS["default"])
        print(f"[INFO] 브랜드 '{brand}'의 디폴트 시나리오 요청 사용")
    else:
        user_request = user_query

    # 시스템 프롬프트에 user_request 주입
    formatted_prompt = SYSTEM_PROMPT.format(user_request=user_request)

    # 최종 프롬프트 구성
    full_prompt = f"{formatted_prompt}\n\n브랜드: {brand}"

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
        temperature=0.2,
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