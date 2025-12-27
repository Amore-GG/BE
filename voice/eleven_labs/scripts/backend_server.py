"""
ElevenLabs TTS Flask Backend Server

사용법:
python backend_server.py
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from elevenlabs.client import ElevenLabs
from elevenlabs.types import VoiceSettings
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # CORS 활성화

API_KEY = "sk_81a58227f843864721833e1b1dee9cbb66312f7234247bbc"
VOICE_ID = "8jHHF8rMqMlg8if2mOUe"
MODEL_ID = "eleven_turbo_v2_5"

# 오디오 저장 폴더
OUTPUT_DIR = "generated_audio"
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.route('/generate', methods=['POST'])
def generate_tts():
    try:
        data = request.json
        text = data.get('text', '')

        if not text:
            return jsonify({'error': '텍스트가 비어있습니다'}), 400

        # Voice & Model ID (Flutter 앱에서 전송)
        voice_id = data.get('voice_id', VOICE_ID)
        model_id = data.get('model_id', MODEL_ID)

        # Voice Settings
        stability = data.get('stability', 0.8)
        similarity_boost = data.get('similarity_boost', 0.8)
        style = data.get('style', 0.4)
        use_speaker_boost = data.get('use_speaker_boost', True)

        # ElevenLabs 클라이언트 초기화
        client = ElevenLabs(api_key=API_KEY)

        # Voice Settings 생성
        voice_settings = VoiceSettings(
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost
        )

        # TTS 생성
        audio_stream = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            voice_settings=voice_settings,
        )

        # 파일 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tts_{timestamp}.mp3"
        filepath = os.path.join(OUTPUT_DIR, filename)

        with open(filepath, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)

        return jsonify({
            'success': True,
            'audio_url': f'/audio/{filename}',
            'filename': filename
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='audio/mpeg')
    return jsonify({'error': 'File not found'}), 404

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("="*60)
    print("ElevenLabs TTS Backend Server")
    print("="*60)
    print(f"Server running on: http://localhost:5000")
    print(f"Audio files saved to: {os.path.abspath(OUTPUT_DIR)}")
    print("="*60)
    app.run(host='0.0.0.0', port=5000, debug=True)
