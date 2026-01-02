"""
발화 품질 검증 모듈
생성된 발화가 규칙을 준수하고 자연스러운지 점검
"""
from typing import Dict, Tuple
import json
import re

VALIDATOR_INSTRUCTION = """You are a dialogue quality validator for Korean influencer content.

**Your Task**: Evaluate the generated dialogue against strict quality criteria.

**Quality Criteria**:
1. **Length**: Must be 1-2 sentences maximum (15-50 characters in Korean)
2. **Uniqueness**: Must NOT repeat or closely resemble previous dialogue
3. **Word Variety**: Must avoid repeating same words/expressions from previous dialogues
   - If previous dialogue used "좋네요", current should use "괜찮은데요", "마음에 들어요", etc.
   - Vary vocabulary: "진짜" → "정말" → "완전" → "너무"
   - Keep language fresh and diverse across scenes
4. **Specificity**: Must be specific to the current scene action, NOT generic
5. **Naturalness**: Must sound like SPONTANEOUS speech in the moment, NOT narration or vlog-style commentary
6. **Korean**: Must be in proper Korean language
7. **CRITICAL - Scene Relevance**: Dialogue MUST directly relate to what's happening in the scene
   - If scene shows "applying product", dialogue should be about the product/application
   - If scene shows "picking up bottle", dialogue should be about the bottle/action
   - NEVER talk about unrelated topics (photos, weather, forest, etc.)
8. **Tone**: Use friendly 해요체, NOT formal 합니다체, and NOT overly casual 반말

**CRITICAL - What to PENALIZE (낮은 점수)**:
- **SCENE MISMATCH (0-3점)**: Dialogue talks about something completely different from the scene
  * Scene: "제품을 바름" → Dialogue: "비 오는 숲 사진이 좋아요" ❌❌❌
  * Scene: "침대에서 일어남" → Dialogue: "이 크림 정말 추천해요" ❌❌❌
  * Scene: "에센스 병을 집음" → Dialogue: "날씨가 좋네요" ❌❌❌
- **WORD REPETITION (4-6점)**: Repeating same words from previous dialogues
  * Previous: "향이 좋네요" → Current: "색감이 좋네요" (repeating "좋네요" - reduce 2-3 points ❌)
  * Previous: "진짜 좋아요" → Current: "진짜 마음에 들어요" (repeating "진짜" - reduce 1-2 points ❌)
  * Should vary vocabulary across scenes for natural conversation flow
- Vlog/narration style: "오늘은 제 루틴을 보여드릴게요", "함께 해봐요", "~를 해볼게요"
- Formal/stiff language: "~합니다", "~드리겠습니다", "~하도록 하겠습니다"
- Explaining actions to camera: "이제 ~를 해볼 거예요", "다음으로 ~를 진행하겠습니다"
- Teaching/tutorial tone: "~하면 좋아요", "~하는 게 중요해요"
- Step-by-step narration: "먼저 ~해요", "그 다음에 ~해요"
- Generic commentary: "추천드려요", "좋은 것 같아요"

**CRITICAL - What to AVOID (must penalize)**:
- Elongated hesitations with "...": "으...", "음...", "아..." (6-7점 감점 ❌)

**GOOD - What to REWARD (높은 점수)**:
- Natural feelings/thoughts (해요체): "기분 좋네요", "상큼해요"
- Direct reactions (해요체): "진짜 좋은데요", "완전 제 스타일이에요"
- Simple observations (해요체): "날씨 정말 좋네요", "향이 좋아요"
- Natural self-talk (해요체): "이 정도면 될까요?", "오늘 피부 괜찮은데요?"
- Exclamations are OK but not required: "와", "오"

**Scoring** (0-10):
- 10: Perfect - spontaneous speech, casual tone, specific reaction
- 7-9: Good - natural but could be more spontaneous
- 4-6: Mediocre - too vlog-like or formal, should regenerate
- 0-3: Poor - narration style or formal language, must regenerate

**Examples of BAD dialogue (점수 낮음)**:
- Scene: "제품을 바름" → "비 오는 숲에서 찍은 사진이 진짜 좋아요!" (0-2점 - SCENE MISMATCH ❌❌❌)
- Scene: "에센스 병을 집음" → "오늘 날씨 정말 좋네요" (0-2점 - irrelevant ❌❌❌)
- "오늘은 제 루틴을 보여드릴게요" (3-4점 - vlog narration)
- "먼저 세안부터 해야죠" (4-5점 - explaining action step-by-step)
- "이제 보습 단계로 넘어갈게요" (4-5점 - narrating next step)
- "제가 요즘 제일 애정하는 제품이에요" (5-6점 - too promotional/vlog-style)
- "손으로 따뜻하게 데워주면 흡수가 더 잘 돼요" (5-6점 - teaching/tutorial tone)

**Examples of GOOD dialogue (점수 높음)**:
- Scene: "창문 열고 햇살 맞음" → "아침 햇살 진짜 좋네요" (9-10점 - PERFECT MATCH ✓)
- Scene: "침대에서 일어남" → "오, 일어나기 싫은데요" (9-10점 - spontaneous, matches scene ✓)
- Scene: "에센스 냄새 맡음" → "와, 향 좋은데요?" (9-10점 - direct reaction to scene ✓)
- Scene: "얼굴에 에센스 바름" → "피부가 촉촉해진 느낌이에요" (9-10점 - matches action ✓)
- Scene: "제품 병을 집음" → "이 제품 완전 제 스타일이에요" (8-9점 - relevant to scene ✓)

**Examples to PENALIZE (elongated hesitations)**:
- "으... 일어나기 싫어요" (6-7점 - elongated hesitation, reduce score)
- "음... 이 정도면 될까요?" (6-7점 - elongated hesitation, reduce score)
- "아... 피곤해요" (6-7점 - elongated hesitation, reduce score)

**Output Format** (JSON):
{
  "score": 8,
  "pass": true,
  "issues": ["optional list of specific issues found"],
  "reason": "brief explanation of score"
}

Now evaluate this dialogue:
"""


def load_validator_model():
    """검증용 모델 로드 (EXAONE 재사용)"""
    from prompt_generator import _model, _tokenizer, load_prompt_model
    load_prompt_model()
    return _model, _tokenizer


def validate_dialogue(
    dialogue: str,
    scene_description: str,
    previous_dialogues: list = None,
    threshold: float = 7.0
) -> Tuple[bool, float, Dict]:
    """
    발화 품질 검증

    Args:
        dialogue: 검증할 발화
        scene_description: 현재 장면 설명
        previous_dialogues: 이전 발화 리스트 (중복 확인용)
        threshold: 합격 기준 점수 (기본 7.0)

    Returns:
        (pass, score, validation_result)
    """
    model, tokenizer = load_validator_model()

    # 이전 발화 컨텍스트
    prev_context = ""
    if previous_dialogues and len(previous_dialogues) > 0:
        prev_context = "\n".join([f"- \"{d}\"" for d in previous_dialogues[-3:]])  # 최근 3개만
        prev_context = f"\n\nPrevious Dialogues:\n{prev_context}"

    # 검증 프롬프트 구성
    validation_prompt = f"""{VALIDATOR_INSTRUCTION}

Scene: "{scene_description}"
Generated Dialogue: "{dialogue}"{prev_context}

Evaluate and respond in JSON format:"""

    messages = [{"role": "user", "content": validation_prompt}]

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
        temperature=0.3,  # 더 일관된 평가를 위해 낮은 temperature
        top_p=0.9,
    )

    generated_ids = output[0][input_ids.shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # <think> 태그 제거
    if "<think>" in generated_text:
        parts = generated_text.split("</think>")
        if len(parts) > 1:
            generated_text = parts[1].strip()

    # JSON 파싱
    try:
        # JSON 추출
        json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
        else:
            # JSON 파싱 실패 시 기본 통과
            result = {
                "score": 7.0,
                "pass": True,
                "issues": ["Failed to parse validation result"],
                "reason": "Validation parsing failed, defaulting to pass"
            }
    except json.JSONDecodeError:
        result = {
            "score": 7.0,
            "pass": True,
            "issues": ["JSON decode error"],
            "reason": "Validation error, defaulting to pass"
        }

    score = float(result.get("score", 7.0))
    passed = score >= threshold

    # pass 필드 업데이트
    result["pass"] = passed

    return passed, score, result


def validate_with_retry(
    generate_func,
    scene_description: str,
    previous_dialogues: list = None,
    max_retries: int = 3,
    threshold: float = 7.0,
    **kwargs
) -> Tuple[Dict, int, list]:
    """
    재시도를 포함한 발화 생성 및 검증

    Args:
        generate_func: 발화 생성 함수
        scene_description: 장면 설명
        previous_dialogues: 이전 발화들
        max_retries: 최대 재시도 횟수
        threshold: 합격 점수
        **kwargs: generate_func에 전달할 추가 인자

    Returns:
        (best_result, attempts, validation_history)
    """
    attempts = 0
    validation_history = []
    best_result = None
    best_score = 0.0

    print(f"  [검증] 발화 생성 시작 (목표 점수: {threshold}점 이상)", flush=True)

    while attempts < max_retries:
        attempts += 1

        # 발화 생성
        try:
            result = generate_func(**kwargs)
            if result is None:
                print(f"  [검증] 시도 {attempts}/{max_retries}: 생성 실패 (None 반환)", flush=True)
                continue
            dialogue = result.get("dialogue", "")
        except Exception as e:
            print(f"  [검증] 시도 {attempts}/{max_retries}: 생성 중 오류 - {str(e)}", flush=True)
            continue

        print(f"  [검증] 시도 {attempts}/{max_retries}: \"{dialogue[:40] if dialogue else '(발화 없음)'}...\"", flush=True)

        # 발화가 비어있으면 검증 스킵하고 통과 처리 (1-2개 장면만 허용되므로)
        if not dialogue or dialogue.strip() == "":
            print(f"  [검증] 발화 없음 - 통과 (시각적 장면)", flush=True)
            validation = {
                "score": 10.0,
                "pass": True,
                "issues": [],
                "reason": "No dialogue needed for this visual scene"
            }
            passed = True
            score = 10.0
        else:
            # 검증
            passed, score, validation = validate_dialogue(
                dialogue,
                scene_description,
                previous_dialogues,
                threshold
            )

        validation_history.append({
            "attempt": attempts,
            "dialogue": dialogue,
            "score": score,
            "passed": passed,
            "validation": validation
        })

        print(f"  [검증] 점수: {score:.1f}/10.0 - {'✓ 통과' if passed else '✗ 재생성'}", flush=True)
        if validation.get("reason"):
            print(f"  [검증] 사유: {validation['reason']}", flush=True)

        # 최고 점수 업데이트
        if score > best_score:
            best_score = score
            best_result = result

        # 통과하면 종료
        if passed:
            print(f"  [검증] ✓ 최종 통과 ({attempts}번 시도)", flush=True)
            return result, attempts, validation_history

    # 최대 재시도 도달 - 최고 점수 결과 반환
    if best_result is None:
        # 모든 시도가 실패한 경우 기본값 반환
        print(f"  [검증] ! 모든 시도 실패 - 기본 프롬프트 사용", flush=True)
        from prompt_generator import get_default_prompts
        best_result = get_default_prompts()
    else:
        print(f"  [검증] ! 최대 시도 도달 - 최고 점수 결과 사용 ({best_score:.1f}점)", flush=True)

    return best_result, attempts, validation_history


if __name__ == "__main__":
    # 테스트
    print("=== 발화 검증 테스트 ===\n")

    test_cases = [
        {
            "dialogue": "안녕하세요, 지지예요! 오늘은 제 루틴을 보여드릴게요.",
            "scene": "지지가 침대에서 일어남",
            "should_fail": True,  # Generic phrase
            "reason": "Generic phrase 사용"
        },
        {
            "dialogue": "아침 햇살이 정말 기분 좋네요!",
            "scene": "지지가 창문을 열고 햇살을 맞음",
            "should_fail": False,
            "reason": "Specific and natural"
        },
        {
            "dialogue": "오늘은 제가 애정하는 이 에센스를 사용해서 제 아침 스킨케어 루틴을 보여드리면서 여러분과 함께 시작해볼까요?",
            "scene": "지지가 에센스 병을 집음",
            "should_fail": True,  # Too long
            "reason": "Too long (over 2 sentences)"
        },
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['reason']}")
        print(f"  장면: {test['scene']}")
        print(f"  발화: \"{test['dialogue']}\"")

        passed, score, result = validate_dialogue(
            test['dialogue'],
            test['scene']
        )

        print(f"  결과: {'✓ 통과' if passed else '✗ 불합격'} (점수: {score:.1f}/10)")
        print(f"  사유: {result.get('reason', 'N/A')}")

        if test['should_fail'] and passed:
            print(f"  ⚠️  예상과 다름: 불합격해야 하는데 통과함")
        elif not test['should_fail'] and not passed:
            print(f"  ⚠️  예상과 다름: 통과해야 하는데 불합격함")

        print()

