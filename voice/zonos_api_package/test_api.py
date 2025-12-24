"""
Zonos TTS API 테스트 스크립트
"""
import requests
import json

# API 서버 주소
BASE_URL = "http://localhost:8000"

def test_health():
    """헬스 체크 테스트"""
    print("=== 헬스 체크 테스트 ===")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")


def test_generate_basic():
    """기본 음성 생성 테스트"""
    print("=== 기본 음성 생성 테스트 ===")

    payload = {
        "text": "안녕하세요. 테스트 음성입니다.",
        "language": "ko"
    }

    response = requests.post(f"{BASE_URL}/generate", json=payload)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"Success: {result['success']}")
        print(f"Audio file: {result['audio_file']}")
        print(f"Message: {result['message']}")
        print(f"Settings: {json.dumps(result['settings'], indent=2)}\n")
        return result['audio_file']
    else:
        print(f"Error: {response.text}\n")
        return None


def test_generate_custom():
    """커스텀 파라미터로 음성 생성 테스트"""
    print("=== 커스텀 음성 생성 테스트 ===")

    payload = {
        "text": "이것은 빠르고 표현력 있는 음성 테스트입니다!",
        "language": "ko",
        "emotion": [0.8, 0.01, 0.01, 0.01, 0.05, 0.01, 0.05, 0.06],  # 행복한 감정
        "speaking_rate": 25.0,  # 빠른 속도
        "pitch_std": 80.0,  # 표현력 있는 음높이
        "cfg_scale": 3.0
    }

    response = requests.post(f"{BASE_URL}/generate", json=payload)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"Success: {result['success']}")
        print(f"Audio file: {result['audio_file']}")
        print(f"Settings: {json.dumps(result['settings'], indent=2)}\n")
        return result['audio_file']
    else:
        print(f"Error: {response.text}\n")
        return None


def test_download_audio(filename):
    """오디오 파일 다운로드 테스트"""
    if not filename:
        print("=== 다운로드 테스트 스킵 (파일명 없음) ===\n")
        return

    print(f"=== 오디오 다운로드 테스트: {filename} ===")

    response = requests.get(f"{BASE_URL}/audio/{filename}")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        output_path = f"downloaded_{filename}"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"파일 저장 완료: {output_path}\n")
    else:
        print(f"Error: {response.text}\n")


def main():
    """모든 테스트 실행"""
    print("Zonos TTS API 테스트 시작\n")
    print("=" * 50)

    # 1. 헬스 체크
    test_health()

    # 2. 기본 음성 생성
    audio_file1 = test_generate_basic()

    # 3. 커스텀 음성 생성
    audio_file2 = test_generate_custom()

    # 4. 오디오 다운로드
    test_download_audio(audio_file1)

    print("=" * 50)
    print("테스트 완료!")


if __name__ == "__main__":
    main()
