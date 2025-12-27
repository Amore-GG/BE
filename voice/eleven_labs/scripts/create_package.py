"""
개발자 인계용 패키지 생성 스크립트

사용법:
python create_package.py
"""

import zipfile
import os
from datetime import datetime

def create_package():
    # 패키지 파일명 (타임스탬프 포함)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"elevenlabs_tts_app_{timestamp}.zip"

    # 포함할 파일 및 폴더
    files_to_include = [
        # 필수 파일
        'backend_server.py',
        'README_FLUTTER.md',
        'FOR_DEVELOPER.md',
        '.env.example',

        # 참고용 파일
        'tts_generator.py',
        'list_models.py',
        'QUICKSTART.md',
    ]

    # Flutter 앱 폴더 내 파일
    flutter_files = [
        'flutter_app/lib/main.dart',
        'flutter_app/pubspec.yaml',
    ]

    # 제외할 폴더/파일 패턴
    exclude_patterns = [
        '.dart_tool',
        'build',
        '.flutter-plugins',
        '.flutter-plugins-dependencies',
        'pubspec.lock',
        'generated_audio',
        '__pycache__',
        '*.pyc',
        '.git',
        'output.mp3',
    ]

    print("="*60)
    print("ElevenLabs TTS App 패키지 생성")
    print("="*60)

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 개별 파일 추가
        for file in files_to_include:
            if os.path.exists(file):
                zipf.write(file, f'elevenlabs_tts/{file}')
                print(f"✓ {file}")
            else:
                print(f"✗ {file} (파일 없음)")

        # Flutter 앱 파일 추가
        for file in flutter_files:
            if os.path.exists(file):
                zipf.write(file, f'elevenlabs_tts/{file}')
                print(f"✓ {file}")

        # Flutter 앱 폴더 전체 추가 (제외 패턴 적용)
        flutter_app_dir = 'flutter_app'
        if os.path.exists(flutter_app_dir):
            for root, dirs, files in os.walk(flutter_app_dir):
                # 제외 폴더 필터링
                dirs[:] = [d for d in dirs if not any(pattern in d for pattern in exclude_patterns)]

                for file in files:
                    # 제외 파일 필터링
                    if any(pattern.replace('*', '') in file for pattern in exclude_patterns):
                        continue

                    file_path = os.path.join(root, file)
                    arcname = os.path.join('elevenlabs_tts', file_path)
                    zipf.write(file_path, arcname)

    file_size = os.path.getsize(zip_filename) / 1024  # KB

    print("="*60)
    print(f"✅ 패키지 생성 완료!")
    print(f"📦 파일명: {zip_filename}")
    print(f"📊 크기: {file_size:.2f} KB")
    print("="*60)
    print("\n다음 내용을 개발자에게 전달하세요:")
    print(f"1. {zip_filename} 파일")
    print("2. API 키 정보:")
    print("   - API_KEY: sk_81a58227f843864721833e1b1dee9cbb66312f7234247bbc")
    print("   - VOICE_ID: 8jHHF8rMqMlg8if2mOUe")
    print("   - MODEL_ID: eleven_turbo_v2_5")
    print("\n압축 해제 후 FOR_DEVELOPER.md를 먼저 읽어보라고 안내하세요.")

if __name__ == "__main__":
    create_package()
