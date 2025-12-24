# Zonos TTS API - 빠른 시작 가이드

## 🚀 5분 안에 시작하기

### 1. API 서버 실행
```bash
python api.py
```
서버가 `http://localhost:8000`에서 실행됩니다.

### 2. 가장 간단한 예시

```html
<!DOCTYPE html>
<html>
<head>
    <title>Zonos TTS 테스트</title>
</head>
<body>
    <h1>Zonos TTS API 테스트</h1>

    <textarea id="text" rows="4" cols="50" placeholder="텍스트를 입력하세요">
안녕하세요. 음성 테스트입니다.
    </textarea><br><br>

    <button onclick="generateSpeech()">음성 생성</button>
    <div id="status"></div>
    <audio id="player" controls style="display:none"></audio>

    <script>
        async function generateSpeech() {
            const text = document.getElementById('text').value;
            const status = document.getElementById('status');
            const player = document.getElementById('player');

            status.textContent = '생성 중...';

            try {
                // 1. 음성 생성 요청
                const response = await fetch('http://localhost:8000/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text })
                });

                const result = await response.json();

                // 2. 오디오 재생
                const audioUrl = `http://localhost:8000/audio/${result.audio_file}`;
                player.src = audioUrl;
                player.style.display = 'block';
                player.play();

                status.textContent = '생성 완료!';
            } catch (error) {
                status.textContent = '오류: ' + error.message;
            }
        }
    </script>
</body>
</html>
```

파일을 저장하고 브라우저에서 열면 됩니다!

---

## 📡 API 엔드포인트 요약

### 음성 생성
```
POST http://localhost:8000/generate
Content-Type: application/json

{
  "text": "안녕하세요"
}
```

### 오디오 재생
```
GET http://localhost:8000/audio/{filename}
```

---

## 🎛️ 파라미터 조정

### 말하기 속도 조절
```javascript
{
  "text": "빠르게 말합니다",
  "speaking_rate": 25.0  // 10=느림, 15=보통, 30=빠름
}
```

### 감정 조절
```javascript
{
  "text": "행복한 목소리입니다",
  "emotion": [0.8, 0.01, 0.01, 0.01, 0.05, 0.01, 0.05, 0.06]  // 행복
}
```

### 언어 변경
```javascript
{
  "text": "Hello, this is a test",
  "language": "en-us"  // ko=한국어, ja=일본어, cmn=중국어
}
```

---

## 🔧 테스트 도구

### cURL로 테스트
```bash
curl -X POST "http://localhost:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{"text":"안녕하세요"}'
```

### Postman으로 테스트
1. Postman 실행
2. POST 요청: `http://localhost:8000/generate`
3. Headers: `Content-Type: application/json`
4. Body (raw JSON):
```json
{
  "text": "안녕하세요"
}
```

---

## ❓ 문제 해결

### 서버 연결 안됨
```bash
# API 서버 상태 확인
curl http://localhost:8000/health
```

### CORS 오류
API 서버에 이미 CORS가 설정되어 있습니다.
문제가 지속되면 브라우저 콘솔 확인.

### 오디오 재생 안됨
- 브라우저에서 직접 URL 접속: `http://localhost:8000/audio/{filename}`
- 파일이 다운로드되면 API는 정상

---

## 📞 추가 정보

자세한 내용은 `WEB_DEVELOPER_GUIDE.md` 참조
