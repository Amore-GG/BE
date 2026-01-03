# EXAONE V2 프롬프트 파이프라인

GIGI 가상 인플루언서 광고 영상 생성 시스템의 전체 파이프라인 문서입니다.

---

## 📊 전체 시스템 아키텍처

```mermaid
flowchart TD
    Start([사용자 시작]) --> Page1[Page 1: 브랜드 선택 & 시나리오 입력]

    Page1 --> CheckScenario{시나리오<br/>입력 여부}

    CheckScenario -->|입력함| UserScenario[사용자 시나리오 사용]
    CheckScenario -->|입력 안함| DefaultScenario[브랜드별 기본 시나리오 사용]

    DefaultScenario --> ScenarioDict[(DEFAULT_SCENARIO_PROMPTS<br/>이니스프리/에뛰드/라네즈)]

    UserScenario --> API1[/POST /generate/]
    ScenarioDict --> API1

    API1 --> InferenceModel[inference_.py<br/>generate_scenario]
    InferenceModel --> EXAONE1[EXAONE 4.0-1.2B<br/>시나리오 생성]

    EXAONE1 --> Validator[scenario_validator.py<br/>문법/띄어쓰기 검증]
    Validator -->|통과| ScenarioText[시나리오 텍스트]
    Validator -->|실패| EXAONE1

    ScenarioText --> Page2[Page 2: 타임테이블 생성]

    Page2 --> VideoDuration[사용자: 영상 길이 입력]
    VideoDuration --> API2[/POST /generate-timetable-stream/]

    API2 --> StreamGen[streaming_timetable.py<br/>generate_timetable_streaming]

    StreamGen --> SceneParser[scenario_parser.py<br/>시나리오 → 장면 분할]

    SceneParser --> TimeCalc[시간 계산<br/>각 장면별 start/end]

    TimeCalc --> LoopScenes{모든 장면<br/>처리 완료?}

    LoopScenes -->|아니오| CurrentScene[현재 장면 처리]

    CurrentScene --> PromptGen[prompt_generator.py<br/>generate_image_prompts]

    PromptGen --> EXAONE2[EXAONE 4.0-1.2B<br/>프롬프트 생성]

    EXAONE2 --> ExtractJSON[extract_json_from_text<br/>JSON 파싱]

    ExtractJSON --> SceneOutput{
        dialogue: 한국어 발화<br/>
        t2i_prompt: 배경/포즈/제품/카메라<br/>
        image_edit_prompt: 편집 지시<br/>
        background_sounds: 배경음
    }

    SceneOutput --> SSE[Server-Sent Events<br/>실시간 스트리밍]

    SSE --> UI[UI: 장면 즉시 표시]

    UI --> LoopScenes

    LoopScenes -->|예| Complete[타임테이블 완성]

    Complete --> UserActions{사용자 액션}

    UserActions -->|발화 재생성| RegenAPI[/POST /regenerate-dialogue/]
    RegenAPI --> DialogueGen[prompt_generator.py<br/>generate_dialogue_only]
    DialogueGen --> EXAONE3[EXAONE 4.0-1.2B<br/>발화만 생성]
    EXAONE3 --> NewDialogue[새 발화]
    NewDialogue --> UpdateUI1[UI 업데이트]

    UserActions -->|발화 직접 수정| EditMode[편집 모드 활성화]
    EditMode --> Textarea[Textarea 입력]
    Textarea --> SaveDialogue[저장 버튼]
    SaveDialogue --> UpdateUI2[UI & 데이터 업데이트]

    UpdateUI1 --> End([완료])
    UpdateUI2 --> End
    Complete --> End

    style Start fill:#e1f5e1
    style End fill:#ffe1e1
    style EXAONE1 fill:#e3f2fd
    style EXAONE2 fill:#e3f2fd
    style EXAONE3 fill:#e3f2fd
    style SceneOutput fill:#fff9c4
    style ScenarioDict fill:#f3e5f5
```

---

## 🔄 주요 프로세스

### 1️⃣ 시나리오 생성 단계

```mermaid
sequenceDiagram
    participant User
    participant Frontend as index.html
    participant API as FastAPI
    participant Inference as inference_.py
    participant Validator as scenario_validator.py
    participant EXAONE as EXAONE Model

    User->>Frontend: 브랜드 선택 & 시나리오 입력
    Frontend->>API: POST /generate

    alt 시나리오 입력 없음
        API->>API: DEFAULT_SCENARIO_PROMPTS[brand]
    end

    API->>Inference: generate_scenario(brand, user_query)
    Inference->>EXAONE: 시나리오 생성 요청
    EXAONE-->>Inference: 생성된 시나리오

    Inference->>Validator: validate_scenario_with_retry()

    loop 최대 3회 재시도
        Validator->>Validator: 문법/띄어쓰기 검사
        alt 점수 < 7.0
            Validator->>EXAONE: 재생성 요청
        else 점수 >= 7.0
            Validator-->>API: 검증된 시나리오
        end
    end

    API-->>Frontend: ScenarioResponse
    Frontend-->>User: 시나리오 표시
```

**핵심 파일:**
- `index.html`: 사용자 입력 UI
- `app.py`: `/generate` API 엔드포인트
- `inference_.py`: EXAONE 모델 호출
- `scenario_validator.py`: 문법/띄어쓰기 검증
- `prompt_generator.py`: `DEFAULT_SCENARIO_PROMPTS` 저장

---

### 2️⃣ 타임테이블 생성 단계 (스트리밍)

```mermaid
sequenceDiagram
    participant User
    participant Frontend as page2.html
    participant API as FastAPI
    participant Streaming as streaming_timetable.py
    participant Parser as scenario_parser.py
    participant PromptGen as prompt_generator.py
    participant EXAONE as EXAONE Model

    User->>Frontend: 영상 길이 입력 (예: 25초)
    Frontend->>API: POST /generate-timetable-stream

    API->>Streaming: generate_timetable_streaming()
    Streaming->>Parser: 시나리오 → 장면 분할
    Parser-->>Streaming: 장면 리스트

    Streaming->>Streaming: 시간 계산 (start/end)

    loop 각 장면마다
        Streaming->>PromptGen: generate_image_prompts(scene)
        PromptGen->>EXAONE: 프롬프트 생성 요청
        EXAONE-->>PromptGen: JSON 응답
        PromptGen->>PromptGen: extract_json_from_text()
        PromptGen-->>Streaming: 프롬프트 데이터

        Streaming->>API: SSE Event (scene)
        API-->>Frontend: data: {"type": "scene", "data": {...}}
        Frontend->>Frontend: appendScene() - 즉시 표시
    end

    Streaming->>API: SSE Event (complete)
    API-->>Frontend: data: {"type": "complete"}
    Frontend-->>User: 타임테이블 완성
```

**핵심 파일:**
- `page2.html`: 타임테이블 UI & 스트리밍 수신
- `app.py`: `/generate-timetable-stream` API
- `streaming_timetable.py`: SSE 스트리밍 생성
- `scenario_parser.py`: 시나리오 파싱
- `prompt_generator.py`: 프롬프트 생성

---

### 3️⃣ 발화 관리 단계

```mermaid
flowchart LR
    A[타임테이블 완성] --> B{사용자 액션}

    B -->|🔄 재생성| C[regenerateDialogue 호출]
    B -->|✏️ 수정| D[enableEditDialogue 호출]
    B -->|발화 클릭| D

    C --> E[POST /regenerate-dialogue]
    E --> F[generate_dialogue_only]
    F --> G[EXAONE 모델]
    G --> H[새 발화 생성]
    H --> I[화면 & 데이터 업데이트]

    D --> J[편집 모드 활성화]
    J --> K[Textarea 표시]
    K --> L[사용자 타이핑]
    L --> M{액션}
    M -->|💾 저장| N[saveDialogue]
    M -->|취소| O[cancelEditDialogue]
    N --> I
    O --> P[원래 값 복원]

    style G fill:#e3f2fd
    style I fill:#c8e6c9
```

**핵심 파일:**
- `page2.html`: 발화 편집 UI & JavaScript 함수
- `app.py`: `/regenerate-dialogue` API
- `prompt_generator.py`: `generate_dialogue_only()` 함수

---

## 📁 핵심 파일 구조

| 파일 | 역할 | 주요 함수/API |
|------|------|---------------|
| **index.html** | Page 1: 브랜드 선택 & 시나리오 입력 UI | - |
| **page2.html** | Page 2: 타임테이블 생성 & 발화 편집 UI | `appendScene()`, `regenerateDialogue()`, `enableEditDialogue()`, `saveDialogue()` |
| **app.py** | FastAPI 백엔드 서버 | `POST /generate`, `POST /generate-timetable-stream`, `POST /regenerate-dialogue` |
| **inference_.py** | 시나리오 생성 (EXAONE 호출) | `generate_scenario()`, `load_model()` |
| **scenario_validator.py** | 문법/띄어쓰기 검증 (최대 3회 재시도) | `validate_scenario_with_retry()` |
| **streaming_timetable.py** | 타임테이블 스트리밍 생성 | `generate_timetable_streaming()` (generator) |
| **scenario_parser.py** | 시나리오 → 장면 분할 | `parse_scenario()` |
| **prompt_generator.py** | 프롬프트 & 발화 생성 | `generate_image_prompts()`, `generate_dialogue_only()`, `generate_scenario()`, `DEFAULT_SCENARIO_PROMPTS` |

---

## 🎯 데이터 흐름

### 시나리오 생성
```
사용자 입력/기본값
  ↓
inference_.py → EXAONE → scenario_validator.py
  ↓
검증된 시나리오 텍스트
```

### 타임테이블 생성
```
시나리오 텍스트
  ↓
scenario_parser.py → 장면 분할
  ↓
각 장면마다:
  prompt_generator.py → EXAONE → JSON 파싱
  ↓
  SSE 스트리밍 → UI 즉시 표시
```

### 발화 재생성
```
장면 설명 + 이전 발화들
  ↓
prompt_generator.generate_dialogue_only()
  ↓
EXAONE → 새 발화 → UI 업데이트
```

---

## 🔑 주요 특징

### 1. **스트리밍 방식**
- Server-Sent Events (SSE)를 사용하여 장면을 하나씩 실시간 전송
- 사용자는 기다리지 않고 생성되는 장면을 즉시 확인 가능

### 2. **브랜드별 기본 시나리오**
```python
DEFAULT_SCENARIO_PROMPTS = {
    "이니스프리": "관엽식물이 있는 화이트 + 그린+ 우드 컬러의...",
    "에뛰드": "지지가 전신거울 앞에서 오늘 입은 옷을...",
    "라네즈": "지지가 하얀 배경의 스튜디오 OR 집에서...",
    # ...
}
```

### 3. **발화 이중 관리**
- **AI 재생성**: 버튼 클릭 → API 호출 → EXAONE 생성
- **직접 수정**: Textarea 편집 → 저장 버튼

### 4. **단어 반복 방지**
- 이전 3개 장면의 발화를 참고
- EXAONE에게 다른 표현 사용 지시

### 5. **GIGI 솔로 비디오 강제**
- 모든 장면에서 지지만 등장
- 다른 사람 언급 금지
- 독백 형식 (monologue)

---

## 🚀 실행 흐름 요약

1. **사용자**: 브랜드 선택 (예: 이니스프리)
2. **시스템**: 기본 시나리오 로드 또는 사용자 입력 사용
3. **EXAONE**: 시나리오 생성 → 검증 (최대 3회)
4. **사용자**: 영상 길이 입력 (예: 25초)
5. **시스템**:
   - 시나리오 파싱 → 장면 분할
   - 각 장면마다 EXAONE으로 프롬프트 생성
   - SSE로 실시간 전송 → UI에 즉시 표시
6. **사용자**: 발화 수정 (AI 재생성 또는 직접 타이핑)
7. **완료**: 타임테이블 완성

---

## 📌 API 엔드포인트

| Method | Endpoint | 설명 | Request | Response |
|--------|----------|------|---------|----------|
| POST | `/generate` | 시나리오 생성 | `{brand, user_query}` | `{scenario, brand, query}` |
| POST | `/generate-timetable-stream` | 타임테이블 스트리밍 생성 | `{scenario, video_duration, brand}` | SSE Stream |
| POST | `/regenerate-dialogue` | 발화 재생성 | `{scene_description, previous_dialogues}` | `{status, dialogue}` |
| GET | `/brands` | 브랜드 목록 조회 | - | `{brands: [...]}` |
| GET | `/health` | 서버 상태 확인 | - | `{status: "ok"}` |

---

## 📝 JSON 출력 형식

### 타임테이블 Scene 데이터
```json
{
  "index": 0,
  "time_start": 0.0,
  "time_end": 4.2,
  "scene_description": "지지가 침대에 앉아...",
  "dialogue": "아침 햇살 진짜 좋네요.",
  "background_sounds_prompt": "birds chirping, window opening sound",
  "t2i_prompt": {
    "background": "bedroom with window, morning sunlight streaming in",
    "character_pose_and_gaze": "Gigi standing by window, arms raised",
    "product": "none",
    "camera_angle": "side angle capturing window light"
  },
  "image_edit_prompt": {
    "pose_change": "open curtains and raise arms",
    "gaze_change": "looking out window",
    "expression": "refreshed morning smile",
    "additional_edits": "add sunlight rays"
  }
}
```

---

## 🛠️ 기술 스택

- **Frontend**: HTML, CSS, JavaScript (Vanilla)
- **Backend**: FastAPI (Python)
- **AI Model**: EXAONE 4.0-1.2B
- **Streaming**: Server-Sent Events (SSE)
- **Validation**: 문법/띄어쓰기 검사 (최대 3회 재시도)

---

## 📚 참고

- 모든 발화는 **한국어**로 생성
- 모든 이미지 프롬프트는 **영어**로 생성
- 배경음 프롬프트도 **영어**로 생성
- 지지는 **여성 가상 인플루언서**로 고정
- **솔로 비디오** 형식 (다른 사람 등장 금지)
