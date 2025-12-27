"""
ElevenLabs 사용 가능한 모델 목록 확인

사용법:
python list_models.py
"""

from elevenlabs.client import ElevenLabs

API_KEY = "sk_81a58227f843864721833e1b1dee9cbb66312f7234247bbc"

def list_available_models():
    client = ElevenLabs(api_key=API_KEY)

    print("="*60)
    print("ElevenLabs 사용 가능한 모델 목록")
    print("="*60)

    try:
        # 모델 목록 가져오기
        models = client.models.get_all()

        for model in models:
            print(f"\n모델 ID: {model.model_id}")
            print(f"  이름: {model.name}")
            print(f"  설명: {model.description if hasattr(model, 'description') else 'N/A'}")
            print(f"  언어: {model.languages if hasattr(model, 'languages') else 'N/A'}")
            print(f"  토큰 비용: {model.token_cost_factor if hasattr(model, 'token_cost_factor') else 'N/A'}")
            print("-" * 60)

    except Exception as e:
        print(f"오류 발생: {e}")
        print("\n알려진 모델 ID (2024년 12월 기준):")
        print("  - eleven_monolingual_v1")
        print("  - eleven_multilingual_v1")
        print("  - eleven_multilingual_v2")
        print("  - eleven_turbo_v2")
        print("  - eleven_turbo_v2_5")
        print("  - eleven_flash_v2")
        print("  - eleven_flash_v2_5")

if __name__ == "__main__":
    list_available_models()
