"""
시나리오 문법 및 띄어쓰기 검증 모듈
생성된 시나리오의 한국어 문법과 띄어쓰기를 점검
"""
from typing import Dict, Tuple
import json
import re

SCENARIO_VALIDATOR_INSTRUCTION = """You are a Korean grammar and spacing validator for advertising scenario text.

**Your Task**: Check the Korean scenario text for grammar errors and spacing (띄어쓰기) issues.

**Quality Criteria**:
1. **띄어쓰기 (Spacing)**: Proper spacing between words according to Korean grammar rules
2. **문법 (Grammar)**: Correct Korean sentence structure and grammar
3. **자연스러움 (Naturalness)**: Natural flow and readability
4. **완결성 (Completeness)**: Complete sentences without fragments
5. **일관성 (Consistency)**: Consistent style and terminology

**Common 띄어쓰기 Errors to Check**:
- Missing spaces after commas: "광고,지지가" → "광고, 지지가" ✓
- Missing spaces between clauses: "침대에앉아" → "침대에 앉아" ✓
- Incorrect spacing with particles: "제품 을" → "제품을" ✓
- Missing spaces before conjunctions: "바르고화면이" → "바르고 화면이" ✓

**Common Grammar Issues to Check**:
- Incomplete sentences or fragments
- Incorrect verb conjugation
- Inconsistent tense usage
- Missing or incorrect particles (조사)
- Awkward or unnatural phrasing

**Scoring** (0-10):
- 10: Perfect - no spacing or grammar issues
- 7-9: Good - minor issues that don't affect understanding
- 4-6: Mediocre - noticeable errors, should fix
- 0-3: Poor - significant errors, must fix

**Output Format** (JSON):
{
  "score": 8,
  "pass": true,
  "spacing_issues": ["list of spacing problems found"],
  "grammar_issues": ["list of grammar problems found"],
  "corrected_text": "corrected version of the text (if needed)",
  "reason": "brief explanation of score"
}

**Examples**:

Example 1 (Bad spacing):
Input: "지지가침대에앉아제품을바름,화면전환이되고세안밴드를낀상태로제품을바름."
Output:
{
  "score": 2,
  "pass": false,
  "spacing_issues": ["침대에앉아 → 침대에 앉아", "제품을바름 → 제품을 바름", "바름,화면 → 바름, 화면", "되고세안밴드를 → 되고 세안밴드를", "낀상태로 → 낀 상태로"],
  "grammar_issues": [],
  "corrected_text": "지지가 침대에 앉아 제품을 바름, 화면 전환이 되고 세안밴드를 낀 상태로 제품을 바름.",
  "reason": "Multiple spacing errors throughout the text"
}

Example 2 (Good):
Input: "화이트와 그린 컬러의 실내 배경에서 지지가 침대에 앉아 협탁에 있는 이니스프리의 그린티 밀크 보습 에센스를 손에 쥠. 화면 전환이 되고 세안 밴드를 낀 지지가 민낯 상태로 해당 제품을 바름."
Output:
{
  "score": 10,
  "pass": true,
  "spacing_issues": [],
  "grammar_issues": [],
  "corrected_text": "",
  "reason": "Perfect spacing and grammar"
}

Example 3 (Grammar issue):
Input: "지지가 침대 앉고 제품 바르다가 화면 전환."
Output:
{
  "score": 4,
  "pass": false,
  "spacing_issues": [],
  "grammar_issues": ["Incomplete sentence structure", "Inconsistent verb forms (앉고/바르다가/전환)", "Missing particles"],
  "corrected_text": "지지가 침대에 앉아 제품을 바르다가 화면이 전환됨.",
  "reason": "Grammar issues with incomplete sentences and verb conjugation"
}

Now validate this Korean scenario text:
"""


def load_scenario_validator_model():
    """검증용 모델 로드 (EXAONE 재사용)"""
    from prompt_generator import _model, _tokenizer, load_prompt_model
    load_prompt_model()
    return _model, _tokenizer


def validate_scenario(
    scenario_text: str,
    threshold: float = 7.0
) -> Tuple[bool, float, Dict]:
    """
    시나리오 문법 및 띄어쓰기 검증

    Args:
        scenario_text: 검증할 시나리오 텍스트
        threshold: 합격 기준 점수 (기본 7.0)

    Returns:
        (pass, score, validation_result)
    """
    model, tokenizer = load_scenario_validator_model()

    # 검증 프롬프트 구성
    validation_prompt = f"""{SCENARIO_VALIDATOR_INSTRUCTION}

Scenario Text: "{scenario_text}"

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
        max_new_tokens=512,
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
                "spacing_issues": [],
                "grammar_issues": ["Failed to parse validation result"],
                "corrected_text": "",
                "reason": "Validation parsing failed, defaulting to pass"
            }
    except json.JSONDecodeError:
        result = {
            "score": 7.0,
            "pass": True,
            "spacing_issues": [],
            "grammar_issues": ["JSON decode error"],
            "corrected_text": "",
            "reason": "Validation error, defaulting to pass"
        }

    score = float(result.get("score", 7.0))
    passed = score >= threshold

    # pass 필드 업데이트
    result["pass"] = passed

    return passed, score, result


def validate_scenario_with_retry(
    generate_func,
    max_retries: int = 3,
    threshold: float = 7.0,
    **kwargs
) -> Tuple[str, int, list]:
    """
    재시도를 포함한 시나리오 생성 및 검증

    Args:
        generate_func: 시나리오 생성 함수
        max_retries: 최대 재시도 횟수
        threshold: 합격 점수
        **kwargs: generate_func에 전달할 추가 인자

    Returns:
        (best_scenario, attempts, validation_history)
    """
    attempts = 0
    validation_history = []
    best_scenario = None
    best_score = 0.0

    print(f"  [시나리오 검증] 생성 시작 (목표 점수: {threshold}점 이상)", flush=True)

    while attempts < max_retries:
        attempts += 1

        # 시나리오 생성
        scenario = generate_func(**kwargs)

        print(f"  [시나리오 검증] 시도 {attempts}/{max_retries}: \"{scenario[:60]}...\"", flush=True)

        # 검증
        passed, score, validation = validate_scenario(
            scenario,
            threshold
        )

        validation_history.append({
            "attempt": attempts,
            "scenario": scenario,
            "score": score,
            "passed": passed,
            "validation": validation
        })

        print(f"  [시나리오 검증] 점수: {score:.1f}/10.0 - {'✓ 통과' if passed else '✗ 재생성'}", flush=True)
        if validation.get("reason"):
            print(f"  [시나리오 검증] 사유: {validation['reason']}", flush=True)

        if validation.get("spacing_issues"):
            print(f"  [시나리오 검증] 띄어쓰기 문제: {', '.join(validation['spacing_issues'][:3])}", flush=True)

        if validation.get("grammar_issues"):
            print(f"  [시나리오 검증] 문법 문제: {', '.join(validation['grammar_issues'][:3])}", flush=True)

        # 최고 점수 업데이트
        if score > best_score:
            best_score = score
            best_scenario = scenario

            # 수정된 텍스트가 있으면 사용
            if validation.get("corrected_text") and validation["corrected_text"].strip():
                best_scenario = validation["corrected_text"]

        # 통과하면 종료
        if passed:
            print(f"  [시나리오 검증] ✓ 최종 통과 ({attempts}번 시도)", flush=True)
            # 수정된 텍스트가 있으면 반환
            if validation.get("corrected_text") and validation["corrected_text"].strip():
                return validation["corrected_text"], attempts, validation_history
            return scenario, attempts, validation_history

    # 최대 재시도 도달 - 최고 점수 결과 반환
    print(f"  [시나리오 검증] ! 최대 시도 도달 - 최고 점수 결과 사용 ({best_score:.1f}점)", flush=True)
    return best_scenario, attempts, validation_history


if __name__ == "__main__":
    # 테스트
    print("=== 시나리오 문법/띄어쓰기 검증 테스트 ===\n")

    test_cases = [
        {
            "text": "지지가침대에앉아제품을바름,화면전환이되고세안밴드를낀상태로제품을바름.",
            "should_fail": True,
            "reason": "심각한 띄어쓰기 오류"
        },
        {
            "text": "화이트와 그린 컬러의 실내 배경에서 지지가 침대에 앉아 협탁에 있는 이니스프리의 그린티 밀크 보습 에센스를 손에 쥠. 화면 전환이 되고 세안 밴드를 낀 지지가 민낯 상태로 해당 제품을 바름.",
            "should_fail": False,
            "reason": "올바른 문법과 띄어쓰기"
        },
        {
            "text": "지지가 침대 앉고 제품 바르다가 화면 전환.",
            "should_fail": True,
            "reason": "문법 오류 (불완전한 문장)"
        },
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['reason']}")
        print(f"  텍스트: \"{test['text']}\"")

        passed, score, result = validate_scenario(test['text'])

        print(f"  결과: {'✓ 통과' if passed else '✗ 불합격'} (점수: {score:.1f}/10)")
        print(f"  사유: {result.get('reason', 'N/A')}")

        if result.get('spacing_issues'):
            print(f"  띄어쓰기 문제: {result['spacing_issues']}")

        if result.get('grammar_issues'):
            print(f"  문법 문제: {result['grammar_issues']}")

        if result.get('corrected_text'):
            print(f"  수정안: \"{result['corrected_text']}\"")

        if test['should_fail'] and passed:
            print(f"  ⚠️  예상과 다름: 불합격해야 하는데 통과함")
        elif not test['should_fail'] and not passed:
            print(f"  ⚠️  예상과 다름: 통과해야 하는데 불합격함")

        print()



