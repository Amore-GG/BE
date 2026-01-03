"""
스트리밍 타임테이블 생성 테스트
실제 서버에서 스트리밍이 동작하는지 확인
"""
import requests
import json

def test_streaming():
    url = "http://localhost:8000/generate-timetable-stream"

    test_data = {
        "scenario": "관엽식물이 있는 화이트 + 그린 + 우드 컬러의 실내 집 배경, 지지가 침대에 앉아 침대 앞에 있는 협탁에 손을 뻗어 이니스프리의 '그린티 밀크 보습 에센스'를 손에 쥠, 화면 전환이 되고 세안 밴드를 낀 지지가 민낯 상태로 해당 제품을 바름.",
        "video_duration": 25,
        "brand": "이니스프리"
    }

    print("=== 스트리밍 타임테이블 생성 테스트 ===\n")
    print(f"시나리오: {test_data['scenario'][:50]}...")
    print(f"영상 길이: {test_data['video_duration']}초")
    print(f"브랜드: {test_data['brand']}\n")

    try:
        # 스트리밍 요청
        response = requests.post(
            url,
            json=test_data,
            stream=True,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code != 200:
            print(f"❌ 에러: HTTP {response.status_code}")
            print(response.text)
            return

        print("✅ 스트리밍 시작!\n")

        # 스트리밍 데이터 수신
        scene_count = 0
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')

                if decoded_line.startswith('data: '):
                    event_data = json.loads(decoded_line[6:])

                    if event_data['type'] == 'metadata':
                        print(f"📋 메타데이터 수신:")
                        print(f"   총 장면: {event_data['data']['scene_count']}개")
                        print(f"   영상 길이: {event_data['data']['total_duration']}초\n")

                    elif event_data['type'] == 'scene':
                        scene_count += 1
                        scene = event_data['data']
                        print(f"🎬 장면 {scene_count} 수신:")
                        print(f"   시간: {scene['time_start']}s ~ {scene['time_end']}s")
                        print(f"   설명: {scene['scene_description'][:60]}...")
                        print(f"   발화: \"{scene['dialogue'][:50]}...\"")
                        print(f"   T2I 배경: {scene['t2i_prompt']['background'][:50]}...")
                        print()

                    elif event_data['type'] == 'complete':
                        print(f"✅ 완료! 총 {scene_count}개 장면 생성됨")

                    elif event_data['type'] == 'error':
                        print(f"❌ 에러: {event_data['data']['message']}")

        print("\n=== 테스트 완료 ===")

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_streaming()
