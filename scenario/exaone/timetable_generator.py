from typing import Dict, List
from scenario_parser import parse_scenario
from prompt_generator import generate_image_prompts
from dialogue_validator import validate_with_retry

def generate_timetable(scenario: str, video_duration: int, brand: str = "") -> Dict:
    """
    시나리오와 영상 길이를 입력받아 타임테이블 생성

    Args:
        scenario: 한국어 시나리오 텍스트
        video_duration: 영상 길이 (초 단위)
        brand: 브랜드 이름 (선택)

    Returns:
        {
            "total_duration": 15,
            "timetable": [
                {
                    "time_start": 0,
                    "time_end": 7,
                    "scene_description": "한국어 장면 설명",
                    "t2i_prompt": {...},
                    "image_edit_prompt": {...}
                },
                ...
            ]
        }
    """
    # 1. 시나리오 분석 → 장면 분할
    print(f"시나리오 분석 중... (총 {video_duration}초)")
    scenes = parse_scenario(scenario, video_duration)
    print(f"총 {len(scenes)}개 장면으로 분할됨")

    # 2. 각 장면별 영어 프롬프트 생성
    timetable = []
    context_history = []  # 이전 장면+발화 누적

    for i, scene in enumerate(scenes):
        print(f"\n[{i+1}/{len(scenes)}] 프롬프트 생성 중...")
        print(f"  시간: {scene['time_start']}s ~ {scene['time_end']}s")
        print(f"  장면: {scene['korean_description'][:50]}...")

        # 영어 프롬프트 생성 with validation (최대 3번 재시도)
        previous_dialogues = [ctx['dialogue'] for ctx in context_history]

        prompts, attempts, validation_history = validate_with_retry(
            generate_func=generate_image_prompts,
            scene_description=scene["korean_description"],
            previous_dialogues=previous_dialogues,
            max_retries=3,
            threshold=7.0,
            korean_scene=scene["korean_description"],
            brand=brand,
            previous_context=context_history
        )

        # prompts가 None일 경우 기본값 사용
        if prompts is None:
            from prompt_generator import get_default_prompts
            prompts = get_default_prompts()
            print(f"  ⚠️ 프롬프트 생성 실패 - 기본값 사용")

        current_dialogue = prompts.get("dialogue", "") if prompts else ""
        print(f"  ✓ 발화 ({attempts}번 시도): {current_dialogue[:50] if current_dialogue else '(발화 없음)'}...")

        # 타임테이블 항목 구성
        timetable.append({
            "time_start": scene["time_start"],
            "time_end": scene["time_end"],
            "scene_description": scene["korean_description"],
            "dialogue": current_dialogue,
            "background_sounds_prompt": prompts.get("background_sounds_prompt", ""),
            "t2i_prompt": prompts["t2i_prompt"],
            "image_edit_prompt": prompts["image_edit_prompt"]
        })

        # 다음 장면을 위해 현재 장면+발화를 히스토리에 추가
        context_history.append({
            "scene": scene["korean_description"],
            "dialogue": current_dialogue
        })

    return {
        "total_duration": video_duration,
        "scene_count": len(timetable),
        "timetable": timetable
    }


if __name__ == "__main__":
    # 테스트
    import json

    test_scenario = """관엽식물이 있는 화이트 + 그린 + 우드 컬러의 실내 집 배경, 지지가 침대에 앉아 침대 앞에 있는 협탁에 손을 뻗어 이니스프리의 '그린티 밀크 보습 에센스'를 손에 쥠, 화면 전환이 되고 세안 밴드를 낀 지지가 민낯 상태로 해당 제품을 바름."""

    test_duration = 15
    test_brand = "이니스프리"

    print("=" * 60)
    print("타임테이블 생성 테스트")
    print("=" * 60)
    print(f"\n브랜드: {test_brand}")
    print(f"영상 길이: {test_duration}초")
    print(f"\n시나리오:\n{test_scenario}")
    print("\n" + "=" * 60)

    result = generate_timetable(test_scenario, test_duration, test_brand)

    print("\n" + "=" * 60)
    print("생성 완료!")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))

