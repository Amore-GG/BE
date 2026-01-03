import re
from typing import List, Dict

def parse_scenario(scenario: str, video_duration: int, target_scene_duration: int = 5) -> List[Dict]:
    """
    시나리오를 분석하여 장면 리스트 반환

    Args:
        scenario: 한국어 시나리오 텍스트
        video_duration: 전체 영상 길이 (초 단위)
        target_scene_duration: 목표 장면 길이 (초 단위, 기본 5초)

    Returns:
        [
            {
                "time_start": 0,
                "time_end": 5,
                "korean_description": "지지가 침대에 앉아..."
            },
            ...
        ]
    """
    # 목표 장면 개수 계산 (25초 / 5초 = 5개 장면), 최소 4개
    target_scene_count = max(4, video_duration // target_scene_duration)

    print(f"[파싱] 목표 장면 개수: {target_scene_count}개 ({video_duration}초 / {target_scene_duration}초)")

    # 장면 전환 키워드로 분할
    scene_separators = [
        "화면 전환이 되고",
        "화면 전환되고",
        "화면이 전환되고",
        "그 다음",
        "이후",
        "다음으로",
        "그리고",
        "->",
        "→",
        "장면 전환",
    ]

    # 먼저 구분자를 특수 마커로 치환
    temp_scenario = scenario
    separator_found = False
    for separator in scene_separators:
        if separator in temp_scenario:
            temp_scenario = temp_scenario.replace(separator, " [SCENE_BREAK] ")
            separator_found = True

    # [SCENE_BREAK]로 분할
    if "[SCENE_BREAK]" in temp_scenario:
        raw_scenes = temp_scenario.split("[SCENE_BREAK]")
        print(f"[파싱] 구분자로 {len(raw_scenes)}개 원본 장면 발견")
    else:
        # 구분자가 없으면 문장 단위로 분할 (마침표 기준)
        # 쉼표는 너무 세밀하게 나누므로 제외
        raw_scenes = re.split(r'\.', scenario)
        print(f"[파싱] 마침표로 {len(raw_scenes)}개 원본 장면 분할")

    # 빈 문자열 제거 및 정제
    scenes = []
    for scene in raw_scenes:
        cleaned = scene.strip()
        if cleaned and len(cleaned) > 15:  # 너무 짧은 장면 제외
            scenes.append(cleaned)

    print(f"[파싱] 정제 후: {len(scenes)}개 장면")

    # 장면이 목표보다 많으면 병합, 적으면 분할
    if len(scenes) > target_scene_count * 1.5:
        # 너무 많으면 병합
        print(f"[파싱] 장면이 너무 많음 ({len(scenes)}개) - 병합 시도")
        merged_scenes = []
        scenes_per_group = len(scenes) // target_scene_count

        for i in range(0, len(scenes), scenes_per_group):
            group = scenes[i:i + scenes_per_group]
            merged_scenes.append(" ".join(group))

        scenes = merged_scenes[:target_scene_count]
        print(f"[파싱] 병합 완료: {len(scenes)}개 장면")

    # 장면이 4개 미만이면 무조건 더 세밀하게 분할
    if len(scenes) < 4:
        print(f"[파싱] 장면이 4개 미만 ({len(scenes)}개) - 세밀하게 분할")

        if len(scenes) == 1:
            # 단일 장면: 먼저 쉼표로 분할 시도
            text = scenes[0]
            sentences = re.split(r'[,]', text)
            scenes = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
            print(f"[파싱] 쉼표로 분할: {len(scenes)}개 장면")

        # 여전히 4개 미만이면 문장을 더 세밀하게 분할
        if len(scenes) < 4:
            new_scenes = []
            for scene in scenes:
                # 접속사, 조사 등으로 추가 분할
                parts = re.split(r'(하고|하며|그리고|또한|이후|다음|그 다음)', scene)

                temp = ""
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue

                    if part in ['하고', '하며', '그리고', '또한', '이후', '다음', '그 다음']:
                        if temp:
                            new_scenes.append(temp.strip())
                            temp = ""
                    else:
                        if temp:
                            temp += " " + part
                        else:
                            temp = part

                if temp:
                    new_scenes.append(temp.strip())

            # 너무 짧은 장면 제거
            scenes = [s for s in new_scenes if len(s) > 10]
            print(f"[파싱] 세밀 분할 완료: {len(scenes)}개 장면")

        # 그래도 4개 미만이면 원본을 4등분
        if len(scenes) < 4:
            original_text = scenario.strip()
            chunk_size = len(original_text) // 4
            scenes = []

            for i in range(4):
                start = i * chunk_size
                end = start + chunk_size if i < 3 else len(original_text)
                chunk = original_text[start:end].strip()
                if chunk:
                    scenes.append(chunk)

            print(f"[파싱] 원본을 4등분: {len(scenes)}개 장면")

    elif len(scenes) < target_scene_count // 2:
        # 목표의 절반 미만이면 분할
        print(f"[파싱] 장면이 목표의 절반 미만 ({len(scenes)}개) - 분할")
        if len(scenes) == 1:
            # 단일 장면을 문장 단위로 재분할
            text = scenes[0]
            sentences = re.split(r'[,.]', text)
            scenes = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 15]

            if len(scenes) < target_scene_count:
                # 여전히 부족하면 원본을 target_scene_count개로 균등 분할
                scenes = [scenario.strip() for _ in range(target_scene_count)]
                print(f"[파싱] 원본을 {target_scene_count}개로 복제")

    # 장면이 없거나 4개 미만이면 최소 4개 보장
    if not scenes:
        scenes = [scenario.strip()]
        print("[파싱] 장면 없음 - 전체를 1개 장면으로")

    # 최종적으로 4개 미만이면 4개로 강제 분할
    if len(scenes) < 4:
        print(f"[파싱] 최종 점검: {len(scenes)}개 < 4개 - 강제 4등분")
        original_text = " ".join(scenes)
        chunk_size = max(10, len(original_text) // 4)
        scenes = []

        for i in range(4):
            start = i * chunk_size
            end = min(start + chunk_size, len(original_text)) if i < 3 else len(original_text)
            chunk = original_text[start:end].strip()
            if chunk:
                scenes.append(chunk)

        # 혹시 빈 장면이 있으면 마지막 장면 내용으로 채우기
        while len(scenes) < 4 and scenes:
            scenes.append(scenes[-1])

        print(f"[파싱] 강제 분할 완료: {len(scenes)}개 장면")

    # 각 장면에 시간 할당 (균등 분할)
    scene_count = len(scenes)
    duration_per_scene = video_duration / scene_count

    timetable = []
    for i, scene_desc in enumerate(scenes):
        time_start = round(i * duration_per_scene, 2)
        time_end = round((i + 1) * duration_per_scene, 2)

        # 마지막 장면은 정확히 video_duration으로 끝나도록
        if i == scene_count - 1:
            time_end = video_duration

        timetable.append({
            "time_start": time_start,
            "time_end": time_end,
            "korean_description": scene_desc
        })

    print(f"[파싱] 최종 타임테이블: {len(timetable)}개 장면")
    for i, scene in enumerate(timetable):
        print(f"  {i+1}. {scene['time_start']}s~{scene['time_end']}s: {scene['korean_description'][:30]}...")

    return timetable


if __name__ == "__main__":
    # 테스트
    test_scenario = "관엽식물이 있는 화이트 + 그린 + 우드 컬러의 실내 집 배경, 지지가 침대에 앉아 침대 앞에 있는 협탁에 손을 뻗어 이니스프리의 '그린티 밀크 보습 에센스'를 손에 쥠, 화면 전환이 되고 세안 밴드를 낀 지지가 민낯 상태로 해당 제품을 바름."

    result = parse_scenario(test_scenario, 15)

    print("=== 시나리오 분석 결과 ===")
    for scene in result:
        print(f"\n시간: {scene['time_start']}s ~ {scene['time_end']}s")
        print(f"설명: {scene['korean_description']}")
