# Zonos TTS API

Zonos 음성 합성 모델을 RESTful API로 제공합니다.

## 설치

```bash
# FastAPI 및 의존성 설치
pip install -r requirements_api.txt
```

## 실행

### 1. API 서버 시작

```bash
# 기본 실행
python api.py

# 또는 uvicorn으로 직접 실행
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

서버가 시작되면 `http://localhost:8000`에서 접근 가능합니다.

### 2. API 문서 확인

브라우저에서 다음 주소로 접속하면 자동 생성된 API 문서를 확인할 수 있습니다:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API 엔드포인트

### 1. 헬스 체크
```http
GET /health
```

**응답 예시:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "device": "cuda"
}
```

### 2. 음성 생성
```http
POST /generate
Content-Type: application/json
```

**요청 Body:**
```json
{
  "text": "생성할 텍스트",
  "language": "ko",
  "emotion": [0.3077, 0.0256, 0.0256, 0.0256, 0.0256, 0.0256, 0.2564, 0.3077],
  "fmax": 22050.0,
  "pitch_std": 20.0,
  "speaking_rate": 15.0,
  "max_new_tokens": 2580,
  "cfg_scale": 2.0,
  "min_p": 0.1,
  "speaker_audio_path": "path/to/speaker.mp3"
}
```

**파라미터 설명:**
- `text` (필수): 생성할 텍스트
- `language`: 언어 코드 (기본값: "ko")
- `emotion`: 감정 벡터 [행복, 슬픔, 혐오, 두려움, 놀람, 분노, 기타, 중립]
- `pitch_std`: 음높이 변화 (20-45: 일반, 60-150: 표현력)
- `speaking_rate`: 말하는 속도 (10: 느림, 15: 보통, 30: 빠름)
- `cfg_scale`: CFG 스케일 (1.0~3.0)

**응답 예시:**
```json
{
  "success": true,
  "audio_file": "tts_20250124_123456_a1b2c3d4.wav",
  "message": "음성 생성 완료",
  "settings": {
    "text": "생성할 텍스트",
    "language": "ko",
    "speaking_rate": 15.0,
    "pitch_std": 20.0,
    "cfg_scale": 2.0
  }
}
```

### 3. 오디오 다운로드
```http
GET /audio/{filename}
```

생성된 오디오 파일을 다운로드합니다.

### 4. 오디오 삭제
```http
DELETE /audio/{filename}
```

생성된 오디오 파일을 삭제합니다.

## 사용 예시

### Python (requests)
```python
import requests

# 음성 생성
response = requests.post("http://localhost:8000/generate", json={
    "text": "안녕하세요. 테스트입니다.",
    "language": "ko",
    "speaking_rate": 20.0
})

result = response.json()
audio_filename = result["audio_file"]

# 오디오 다운로드
audio_response = requests.get(f"http://localhost:8000/audio/{audio_filename}")
with open("output.wav", "wb") as f:
    f.write(audio_response.content)
```

### cURL
```bash
# 음성 생성
curl -X POST "http://localhost:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "안녕하세요",
    "language": "ko"
  }'

# 오디오 다운로드
curl -O "http://localhost:8000/audio/tts_20250124_123456_a1b2c3d4.wav"
```

### JavaScript (fetch)
```javascript
// 음성 생성
const response = await fetch('http://localhost:8000/generate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    text: '안녕하세요',
    language: 'ko'
  })
});

const result = await response.json();
console.log(result.audio_file);

// 오디오 다운로드
const audioUrl = `http://localhost:8000/audio/${result.audio_file}`;
```

## 테스트

테스트 스크립트를 실행하여 API가 정상 작동하는지 확인할 수 있습니다:

```bash
python test_api.py
```

## 감정 프리셋

### 중립적
```json
"emotion": [0.3077, 0.0256, 0.0256, 0.0256, 0.0256, 0.0256, 0.2564, 0.3077]
```

### 행복한
```json
"emotion": [0.8, 0.01, 0.01, 0.01, 0.05, 0.01, 0.05, 0.06]
```

### 슬픈
```json
"emotion": [0.01, 0.8, 0.01, 0.01, 0.01, 0.01, 0.05, 0.1]
```

### 화난
```json
"emotion": [0.01, 0.01, 0.1, 0.01, 0.01, 0.7, 0.1, 0.06]
```

## 프로덕션 배포

### 1. Gunicorn 사용
```bash
pip install gunicorn
gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 2. Docker 사용
```dockerfile
FROM python:3.10

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt -r requirements_api.txt

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 주의사항

- 첫 실행 시 모델 로딩에 시간이 걸립니다
- GPU 메모리가 충분한지 확인하세요
- 생성된 오디오 파일은 `generated_audio/` 디렉토리에 저장됩니다
- 주기적으로 생성된 파일을 정리하는 것을 권장합니다
