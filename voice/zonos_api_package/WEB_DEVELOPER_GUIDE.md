# Zonos TTS API - 웹 개발자 가이드

## 📋 목차
1. [개요](#개요)
2. [API 서버 정보](#api-서버-정보)
3. [API 엔드포인트](#api-엔드포인트)
4. [요청/응답 예시](#요청응답-예시)
5. [프론트엔드 구현 예시](#프론트엔드-구현-예시)
6. [CORS 설정](#cors-설정)
7. [에러 처리](#에러-처리)

---

## 개요

Zonos TTS는 텍스트를 음성으로 변환하는 API 서버입니다.
- 다양한 언어 지원 (한국어, 영어, 일본어 등 80개 이상)
- 감정 조절 가능 (행복, 슬픔, 분노 등)
- 음높이, 속도 조절 가능
- 고품질 음성 생성 (22.05kHz/24kHz)

---

## API 서버 정보

### 기본 URL
```
http://localhost:8000
```
프로덕션에서는 실제 서버 URL로 변경하세요.

### 기술 스택
- **Framework**: FastAPI
- **Model**: Zonos TTS (Transformer/Hybrid)
- **Output**: WAV 파일 (16-bit PCM)

---

## API 엔드포인트

### 1. 헬스 체크
서버가 정상 작동하는지 확인합니다.

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

---

### 2. 음성 생성 (핵심 API)
텍스트를 음성으로 변환합니다.

```http
POST /generate
Content-Type: application/json
```

**요청 Body (필수만):**
```json
{
  "text": "안녕하세요. 테스트입니다."
}
```

**요청 Body (전체 옵션):**
```json
{
  "text": "안녕하세요. 테스트입니다.",
  "language": "ko",
  "emotion": [0.3077, 0.0256, 0.0256, 0.0256, 0.0256, 0.0256, 0.2564, 0.3077],
  "fmax": 22050.0,
  "pitch_std": 20.0,
  "speaking_rate": 15.0,
  "max_new_tokens": 2580,
  "cfg_scale": 2.0,
  "min_p": 0.1,
  "speaker_audio_path": null
}
```

**파라미터 설명:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `text` | string | ✅ | - | 생성할 텍스트 |
| `language` | string | ❌ | "ko" | 언어 코드 (ko, en-us, ja 등) |
| `emotion` | array[8] | ❌ | 중립 | 감정 벡터 [행복, 슬픔, 혐오, 두려움, 놀람, 분노, 기타, 중립] |
| `fmax` | float | ❌ | 22050.0 | 최대 주파수 (22050 또는 24000) |
| `pitch_std` | float | ❌ | 20.0 | 음높이 변화 (20-45: 일반, 60-150: 표현력) |
| `speaking_rate` | float | ❌ | 15.0 | 말하기 속도 (10: 느림, 30: 빠름) |
| `max_new_tokens` | int | ❌ | 2580 | 최대 토큰 수 (86 * 30 = 약 30초) |
| `cfg_scale` | float | ❌ | 2.0 | CFG 스케일 (1.0~3.0, 높을수록 조건을 더 따름) |
| `min_p` | float | ❌ | 0.1 | 샘플링 확률 임계값 |
| `speaker_audio_path` | string | ❌ | null | 화자 음성 파일 경로 (서버 내부 경로) |

**응답 예시:**
```json
{
  "success": true,
  "audio_file": "tts_20250124_143022_a1b2c3d4.wav",
  "message": "음성 생성 완료",
  "settings": {
    "text": "안녕하세요. 테스트입니다.",
    "language": "ko",
    "speaking_rate": 15.0,
    "pitch_std": 20.0,
    "cfg_scale": 2.0
  }
}
```

---

### 3. 오디오 파일 다운로드
생성된 음성 파일을 다운로드합니다.

```http
GET /audio/{filename}
```

**예시:**
```http
GET /audio/tts_20250124_143022_a1b2c3d4.wav
```

**응답:**
- Content-Type: `audio/wav`
- WAV 파일 바이너리 데이터

---

### 4. 오디오 파일 삭제
생성된 음성 파일을 삭제합니다.

```http
DELETE /audio/{filename}
```

**응답 예시:**
```json
{
  "success": true,
  "message": "tts_20250124_143022_a1b2c3d4.wav 삭제 완료"
}
```

---

## 요청/응답 예시

### JavaScript (Fetch API)

```javascript
// 1. 음성 생성
async function generateSpeech(text, options = {}) {
  const response = await fetch('http://localhost:8000/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text: text,
      language: options.language || 'ko',
      speaking_rate: options.speakingRate || 15.0,
      pitch_std: options.pitchStd || 20.0,
      emotion: options.emotion || null,
    }),
  });

  if (!response.ok) {
    throw new Error('음성 생성 실패');
  }

  const result = await response.json();
  return result.audio_file;
}

// 2. 오디오 재생
function playAudio(filename) {
  const audioUrl = `http://localhost:8000/audio/${filename}`;
  const audio = new Audio(audioUrl);
  audio.play();
}

// 3. 사용 예시
async function main() {
  try {
    const filename = await generateSpeech('안녕하세요', {
      language: 'ko',
      speakingRate: 20.0,
      pitchStd: 30.0,
    });

    console.log('생성된 파일:', filename);
    playAudio(filename);
  } catch (error) {
    console.error('오류:', error);
  }
}
```

---

### React 예시

```jsx
import { useState } from 'react';

function TTSComponent() {
  const [text, setText] = useState('');
  const [audioUrl, setAudioUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });

      const result = await response.json();
      setAudioUrl(`http://localhost:8000/audio/${result.audio_file}`);
    } catch (error) {
      alert('음성 생성 실패: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="텍스트를 입력하세요"
      />
      <button onClick={handleGenerate} disabled={loading}>
        {loading ? '생성 중...' : '음성 생성'}
      </button>

      {audioUrl && (
        <audio controls src={audioUrl}>
          Your browser does not support audio.
        </audio>
      )}
    </div>
  );
}
```

---

### Vue.js 예시

```vue
<template>
  <div>
    <textarea v-model="text" placeholder="텍스트를 입력하세요"></textarea>
    <button @click="generateSpeech" :disabled="loading">
      {{ loading ? '생성 중...' : '음성 생성' }}
    </button>

    <audio v-if="audioUrl" controls :src="audioUrl"></audio>
  </div>
</template>

<script>
export default {
  data() {
    return {
      text: '',
      audioUrl: null,
      loading: false,
    };
  },
  methods: {
    async generateSpeech() {
      this.loading = true;
      try {
        const response = await fetch('http://localhost:8000/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: this.text }),
        });

        const result = await response.json();
        this.audioUrl = `http://localhost:8000/audio/${result.audio_file}`;
      } catch (error) {
        alert('음성 생성 실패: ' + error.message);
      } finally {
        this.loading = false;
      }
    },
  },
};
</script>
```

---

### jQuery 예시

```javascript
$('#generateBtn').click(function() {
  const text = $('#textInput').val();

  $.ajax({
    url: 'http://localhost:8000/generate',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({ text: text }),
    success: function(result) {
      const audioUrl = `http://localhost:8000/audio/${result.audio_file}`;
      $('#audioPlayer').attr('src', audioUrl);
    },
    error: function(error) {
      alert('음성 생성 실패');
    }
  });
});
```

---

## 감정 프리셋

### 중립 (기본값)
```json
[0.3077, 0.0256, 0.0256, 0.0256, 0.0256, 0.0256, 0.2564, 0.3077]
```

### 행복한
```json
[0.8, 0.01, 0.01, 0.01, 0.05, 0.01, 0.05, 0.06]
```

### 슬픈
```json
[0.01, 0.8, 0.01, 0.01, 0.01, 0.01, 0.05, 0.1]
```

### 화난
```json
[0.01, 0.01, 0.1, 0.01, 0.01, 0.7, 0.1, 0.06]
```

감정 벡터는 총 8개 값으로 구성:
`[행복, 슬픔, 혐오, 두려움, 놀람, 분노, 기타, 중립]`

합이 1.0이 되도록 정규화됩니다.

---

## 지원 언어 목록

주요 언어:
- `ko`: 한국어
- `en-us`: 영어 (미국)
- `en-gb`: 영어 (영국)
- `ja`: 일본어
- `cmn`: 중국어 (만다린)
- `fr-fr`: 프랑스어
- `de`: 독일어
- `es`: 스페인어
- `ru`: 러시아어
- `ar`: 아랍어

총 80개 이상의 언어 지원. 전체 목록은 API 문서 참조.

---

## CORS 설정

현재 API는 모든 Origin에서의 요청을 허용합니다 (`allow_origins=["*"]`).

프로덕션 환경에서는 보안을 위해 특정 도메인만 허용하도록 설정하세요:

```python
# api.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 에러 처리

### 에러 응답 형식

```json
{
  "detail": "에러 메시지"
}
```

### 주요 에러 코드

| 코드 | 의미 | 해결 방법 |
|-----|------|----------|
| 400 | 잘못된 요청 | 요청 파라미터 확인 |
| 404 | 파일 없음 | 파일명 확인 |
| 500 | 서버 오류 | 서버 로그 확인 |
| 503 | 서비스 불가 | 모델 로딩 대기 |

### 에러 처리 예시

```javascript
async function generateSpeechWithErrorHandling(text) {
  try {
    const response = await fetch('http://localhost:8000/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || '음성 생성 실패');
    }

    return await response.json();
  } catch (error) {
    console.error('오류:', error.message);
    // 사용자에게 에러 메시지 표시
    alert(`음성 생성 실패: ${error.message}`);
    return null;
  }
}
```

---

## 성능 고려사항

### 1. 생성 시간
- 첫 요청: 5-10초 (모델 로딩)
- 이후 요청: 2-5초 (텍스트 길이에 따라)

### 2. 파일 크기
- 약 1.4MB/초 (22.05kHz, 16-bit PCM)
- 30초 음성 ≈ 42MB

### 3. 동시 요청
- 현재 서버는 순차 처리
- 동시 요청 시 대기 시간 발생 가능
- 필요시 큐 시스템 구현 권장

---

## 보안 고려사항

1. **API 키 인증** (권장)
   - 현재는 인증 없음
   - 프로덕션에서는 API 키 추가 권장

2. **Rate Limiting**
   - 과도한 요청 방지
   - IP별 요청 제한 권장

3. **입력 검증**
   - 텍스트 길이 제한 (현재 무제한)
   - 악의적인 입력 필터링

---

## 문의 및 지원

문제가 발생하거나 추가 기능이 필요한 경우:
1. API 서버 로그 확인
2. `/health` 엔드포인트로 서버 상태 확인
3. 개발팀에 문의

---

## 체크리스트

웹 개발자가 확인해야 할 사항:

- [ ] API 서버 URL 설정
- [ ] CORS 이슈 확인
- [ ] 오디오 재생 테스트
- [ ] 에러 처리 구현
- [ ] 로딩 상태 UI 구현
- [ ] 모바일 반응형 고려
- [ ] 브라우저 호환성 테스트
- [ ] 파일 다운로드 기능 구현
- [ ] 사용자 피드백 UI 구현

---

## 변경 이력

- 2025-01-24: 초기 버전 작성
