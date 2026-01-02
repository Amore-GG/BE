"""
스트리밍 방식 타임테이블 생성
장면을 하나씩 생성하여 점진적으로 표시
"""
from typing import Dict, Generator
from scenario_parser import parse_scenario
from prompt_generator import generate_image_prompts
from dialogue_validator import validate_with_retry
import json

def generate_timetable_streaming(
    scenario: str,
    video_duration: int,
    brand: str = ""
) -> Generator[Dict, None, None]:
    """
    타임테이블을 스트리밍 방식으로 생성
    각 장면을 생성할 때마다 yield

    Args:
        scenario: 한국어 시나리오
        video_duration: 영상 길이 (초)
        brand: 브랜드명

    Yields:
        {
            "type": "metadata" | "scene" | "complete",
            "data": {...}
        }
    """
    # 1. 메타데이터 전송
    scenes = parse_scenario(scenario, video_duration)
    yield {
        "type": "metadata",
        "data": {
            "total_duration": video_duration,
            "scene_count": len(scenes),
            "status": "started"
        }
    }

    # 2. 각 장면을 순차적으로 생성
    context_history = []  # 이전 장면+발화 누적

    for i, scene in enumerate(scenes):
        print(f"\n[스트리밍] {i+1}/{len(scenes)} 장면 생성 중...", flush=True)
        print(f"  시간: {scene['time_start']}s ~ {scene['time_end']}s", flush=True)
        print(f"  장면: {scene['korean_description'][:60]}...", flush=True)

        if context_history:
            print(f"  이전 컨텍스트: {len(context_history)}개 장면", flush=True)
            for j, ctx in enumerate(context_history, 1):
                print(f"    장면{j}: \"{ctx['dialogue'][:30]}...\"", flush=True)

        # 프롬프트 생성 with validation (최대 3번 재시도)
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
            print(f"  ⚠️ 프롬프트 생성 실패 - 기본값 사용", flush=True)

        current_dialogue = prompts.get("dialogue", "") if prompts else ""
        print(f"  ✓ 발화 ({attempts}번 시도): {current_dialogue[:40] if current_dialogue else '(발화 없음)'}...", flush=True)

        # 장면 데이터 전송
        scene_data = {
            "index": i,
            "time_start": scene["time_start"],
            "time_end": scene["time_end"],
            "scene_description": scene["korean_description"],
            "dialogue": current_dialogue,
            "background_sounds_prompt": prompts.get("background_sounds_prompt", ""),
            "t2i_prompt": prompts["t2i_prompt"],
            "image_edit_prompt": prompts["image_edit_prompt"]
        }

        yield {
            "type": "scene",
            "data": scene_data
        }

        print(f"  ✓ 장면 {i+1} 전송 완료", flush=True)

        # 다음 장면을 위해 현재 장면+발화를 히스토리에 추가
        context_history.append({
            "scene": scene["korean_description"],
            "dialogue": current_dialogue
        })

    # 3. 완료 신호
    yield {
        "type": "complete",
        "data": {
            "status": "completed",
            "total_scenes": len(scenes)
        }
    }


if __name__ == "__main__":
    # 테스트
    test_scenario = """관엽식물이 있는 화이트 + 그린 + 우드 컬러의 실내 집 배경, 지지가 침대에 앉아 침대 앞에 있는 협탁에 손을 뻗어 이니스프리의 '그린티 밀크 보습 에센스'를 손에 쥠, 화면 전환이 되고 세안 밴드를 낀 지지가 민낯 상태로 해당 제품을 바름."""

    print("=== 스트리밍 타임테이블 생성 테스트 ===\n")

    for event in generate_timetable_streaming(test_scenario, 10, "이니스프리"):
        print(f"\n[{event['type'].upper()}]")
        print(json.dumps(event['data'], indent=2, ensure_ascii=False))

