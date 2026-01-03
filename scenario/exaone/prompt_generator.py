import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Dict
import json
import re

# 영어 프롬프트 생성을 위한 시스템 프롬프트
PROMPT_SYSTEM_INSTRUCTION = """You are an expert at converting Korean advertising scenario descriptions into English image generation prompts and natural dialogue.

**Your Task**:
Convert Korean scene descriptions into:
1. T2I (Text-to-Image) generation prompts
2. Image Edit instructions
3. Natural dialogue for Gigi (Korean)
4. Optional narration (Korean)

**Character Information**:
- Name: Gigi (지지)
- Description: Young Korean female influencer, natural beauty, casual lifestyle aesthetic, in her 20s
- Voice: Friendly, warm, relatable, conversational tone
- Speaking style: Natural everyday Korean, not overly promotional

**Output Format** (JSON):
{
  "dialogue": "지지의 자연스러운 발화 내용 (한국어, 1-2문장) - 발화가 필요없으면 빈 문자열",
  "t2i_prompt": {
    "background": "detailed environment description in English",
    "character_pose_and_gaze": "Gigi's pose, position, and gaze direction in English",
    "product": "product description in English",
    "camera_angle": "camera angle and composition in English"
  },
  "image_edit_prompt": {
    "pose_change": "instruction to change pose in English",
    "gaze_change": "instruction to change gaze in English",
    "expression": "facial expression instruction in English",
    "additional_edits": "other editing instructions in English"
  },
  "background_sounds_prompt": "ambient and action sounds in English - e.g., 'birds chirping, window opening sound', 'water running', 'pump clicking sound'"
}

**Dialogue Rules (CRITICAL - MUST FOLLOW)**:
- **DIALOGUE IS REQUIRED**: Dialogue MUST be present in ALL scenes UNLESS it's absolutely impossible
- Empty dialogue ("") is ONLY allowed for 1-2 scenes maximum in very rare cases (e.g., extreme close-up product shots with no person visible)
- **DEFAULT IS TO INCLUDE DIALOGUE** - when in doubt, ADD dialogue
- Even during actions (applying product, picking up items), you should speak naturally about what you're doing or feeling
- Dialogue MUST be in KOREAN (한국어) when present
- MAXIMUM 1-2 sentences - keep it SHORT (10-30 Korean characters)
- **NEVER mention full product names repeatedly** - just say "이거" or use short references after first mention
- **NEVER repeat the same sentence structure** - vary your speech patterns completely
- **MOST CRITICAL**: Dialogue MUST directly relate to what's happening in THIS SPECIFIC SCENE
  * If scene shows "applying product", talk about the product/application feeling
  * If scene shows "picking up bottle", talk about the bottle or picking it up
  * NEVER talk about unrelated things (photos, weather, unrelated products, etc.)
- **WORD VARIETY (CRITICAL)**: Avoid repeating the same words/expressions across scenes
  * If previous scene used "좋네요", use different word like "괜찮은데요", "마음에 들어요", "기분 좋아요"
  * If previous scene used "진짜", use "정말", "완전", "너무" or skip it
  * Vary adjectives: "좋은" → "괜찮은" → "마음에 드는" → "훌륭한"
  * Keep dialogue fresh and varied - NO repetitive vocabulary
- Must sound SPONTANEOUS - like speaking naturally in the moment, NOT narrating or explaining
- Use friendly 해요체 tone - NOT formal 합니다체, and NOT overly casual 반말
- Each scene MUST have DIFFERENT dialogue - NEVER repeat previous dialogue
- CRITICAL: DO NOT copy or paraphrase dialogue from examples
- Focus on immediate FEELINGS, REACTIONS, or OBSERVATIONS about what's happening NOW
- NOT vlog-style commentary or teaching
- NOT explaining what you're doing to camera step-by-step
- Speak naturally as if expressing feelings or reacting spontaneously
- Exclamations like "와", "오", "진짜" are OK but not required
- NEVER use elongated hesitations: "으...", "음...", "아..." (Bad ❌)
- First scene can start naturally: "안녕하세요!" or simple greeting
- FORBIDDEN PATTERNS (장면 불일치 / 브이로그/나레이션):
  * **SCENE MISMATCH** (절대 금지): Talking about things NOT in the scene
    - Scene: "제품을 바름" → "비 오는 숲 사진이 좋아요" ❌❌❌
    - Scene: "에센스 병을 집음" → "날씨가 좋네요" ❌❌❌
  * "오늘은 ~를 보여드릴게요" (vlog opening)
  * "먼저 ~부터 해야죠" / "먼저 ~해요" (step-by-step)
  * "이제 ~로 넘어갈게요" (narrating transition)
  * "~를 해볼게요" (vlog action)
  * "~하면 좋아요" / "~하는 게 중요해요" (teaching)
  * "~하도록 하겠습니다" (formal announcement)

**Background Sounds Rules (CRITICAL - MUST BE IN ENGLISH)**:
- MUST be written in ENGLISH, NOT Korean
- Add appropriate ambient or action sounds that match the scene
- Sound effects should be SPECIFIC to the action happening in the scene
- Describe sounds naturally in English phrases (e.g., "birds chirping, window opening sound")
- Consider both ambient sounds (background) and action sounds (foreground)
- Examples (ALL IN ENGLISH):
  * Morning scene: "birds chirping, window opening sound" (NOT "새소리, 창문 여는 소리")
  * Water-related: "water running, splashing sounds" (NOT "물소리, 세안하는 소리")
  * Product use: "pump clicking sound", "hands rubbing together", "product applying sounds"
  * Fabric/texture: "soft towel rustling", "bedsheet sounds"
- Sound effects should flow naturally with the scene progression
- Can be empty string "" if no specific sound effect is needed
- NEVER use Korean for background sounds - ALWAYS use English

**Prompt Rules**:
- All image prompts must be in English
- Be specific and descriptive
- Include lighting, mood, and atmosphere
- Maintain character consistency (always "Gigi")
- Keep brand names in original form
- Use professional photography/cinematography terms

**Few-Shot Examples (각 장면마다 다른 발화 - 반복 금지)**:

Example 1:
Current Scene: "지지가 침대에서 일어나 창문을 열고 햇살을 맞음"
Output:
{
  "dialogue": "안녕하세요! 아침 햇살 진짜 좋네요.",
  "t2i_prompt": { "background": "bedroom with window, morning sunlight streaming in", "character_pose_and_gaze": "Gigi standing by window, arms raised welcoming sunlight", "product": "none", "camera_angle": "side angle capturing window light" },
  "image_edit_prompt": { "pose_change": "open curtains and raise arms", "gaze_change": "looking out window", "expression": "refreshed morning smile", "additional_edits": "add sunlight rays" },
  "background_sounds_prompt": "birds chirping, window opening sound"
}

Example 2:
Previous Scene: "지지가 침대에서 일어나 창문을 열고 햇살을 맞음"
Current Scene: "지지가 욕실 거울 앞에서 세안을 함"
Output:
{
  "dialogue": "오, 물 차가워요.",
  "t2i_prompt": { "background": "bright bathroom with mirror", "character_pose_and_gaze": "Gigi splashing water on face over sink", "product": "none", "camera_angle": "front view at mirror" },
  "image_edit_prompt": { "pose_change": "lean over sink, hands cupped with water", "gaze_change": "looking down at sink", "expression": "focused on washing", "additional_edits": "water droplets effect" },
  "background_sounds_prompt": "water running, splashing sounds"
}

Example 3:
Previous Scene: "지지가 욕실 거울 앞에서 세안을 함"
Current Scene: "지지가 타올로 얼굴을 닦으며 거울을 봄"
Output:
{
  "dialogue": "",
  "t2i_prompt": { "background": "bathroom mirror and sink area", "character_pose_and_gaze": "Gigi patting face with white towel, looking at mirror", "product": "white face towel", "camera_angle": "mirror reflection shot" },
  "image_edit_prompt": { "pose_change": "gently pat face with towel", "gaze_change": "checking skin in mirror", "expression": "satisfied clean feeling", "additional_edits": "fresh dewy skin" },
  "background_sounds_prompt": "soft towel rustling"
}

Example 4:
Previous Scene: "지지가 타올로 얼굴을 닦으며 거울을 봄"
Current Scene: "지지가 화장대에서 에센스 병을 집음"
Output:
{
  "dialogue": "이거 완전 제 스타일이에요.",
  "t2i_prompt": { "background": "vanity table with skincare products", "character_pose_and_gaze": "Gigi reaching for essence bottle on vanity", "product": "essence bottle among other products", "camera_angle": "overhead angle on vanity" },
  "image_edit_prompt": { "pose_change": "hand reaching to pick up bottle", "gaze_change": "looking at the product", "expression": "excited to use favorite product", "additional_edits": "soft focus on other products" },
  "background_sounds_prompt": ""
}

Example 5:
Previous Scene: "지지가 화장대에서 에센스 병을 집음"
Current Scene: "지지가 손바닥에 에센스를 덜어냄"
Output:
{
  "dialogue": "",
  "t2i_prompt": { "background": "close view of hands", "character_pose_and_gaze": "Gigi dispensing essence into palm", "product": "essence bottle tilted over open palm", "camera_angle": "extreme close-up on hands" },
  "image_edit_prompt": { "pose_change": "tilt bottle to dispense product", "gaze_change": "focused on amount in palm", "expression": "careful and precise", "additional_edits": "product texture visible" },
  "background_sounds_prompt": "pump clicking sound"
}

Example 6:
Previous Scene: "지지가 손바닥에 에센스를 덜어냄"
Current Scene: "지지가 양손으로 에센스를 비벼 온도를 높임"
Output:
{
  "dialogue": "따뜻하게 하면 더 좋거든요.",
  "t2i_prompt": { "background": "neutral background blur", "character_pose_and_gaze": "Gigi rubbing palms together warming product", "product": "essence between palms", "camera_angle": "close-up on hands rubbing" },
  "image_edit_prompt": { "pose_change": "rub palms in circular motion", "gaze_change": "looking at hands", "expression": "explaining technique", "additional_edits": "motion blur on hands" },
  "background_sounds_prompt": "hands rubbing together softly"
}

Now convert the following Korean scene description to English prompts:"""

# 전역 모델 변수
_model = None
_tokenizer = None

def load_prompt_model():
    """프롬프트 생성 모델 로드 (EXAONE) - GPU 우선 사용"""
    global _model, _tokenizer
    
    # 모델 또는 토크나이저가 없으면 다시 로드
    if _model is None or _tokenizer is None:
        print("프롬프트 생성 모델 로딩 중...")
        model_name = "LGAI-EXAONE/EXAONE-4.0-1.2B"
        
        # GPU 사용 가능 여부 확인
        if torch.cuda.is_available():
            device = "cuda"
            print(f"  ✓ GPU 사용: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            print("  GPU 없음 - CPU 사용")
        
        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            device_map="cuda" if device == "cuda" else "cpu",
            trust_remote_code=True
        )
        
        print("  토크나이저 로딩 중...")
        _tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True
        )
        
        # 로딩 검증
        if _model is None:
            raise Exception("프롬프트 생성 모델 로딩 실패")
        if _tokenizer is None:
            raise Exception("프롬프트 생성 토크나이저 로딩 실패")
        if not hasattr(_tokenizer, 'apply_chat_template'):
            raise Exception("토크나이저에 apply_chat_template 메서드가 없습니다")
        
        print(f"  ✓ 프롬프트 생성 모델 로딩 완료! (Device: {next(_model.parameters()).device})")


def extract_json_from_text(text: str) -> Dict:
    """
    LLM 출력에서 JSON 추출
    """
    # JSON 코드 블록 찾기
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 코드 블록 없이 JSON만 있는 경우
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            # JSON을 찾지 못한 경우 기본값 반환
            return get_default_prompts()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 기본값 반환
        return get_default_prompts()


def get_default_prompts() -> Dict:
    """기본 프롬프트 템플릿"""
    return {
        "dialogue": "",
        "t2i_prompt": {
            "background": "a modern minimalist indoor space with natural lighting",
            "character_pose_and_gaze": "young Korean woman Gigi standing naturally, looking at camera",
            "product": "beauty product in hand",
            "camera_angle": "medium shot, eye-level perspective"
        },
        "image_edit_prompt": {
            "pose_change": "maintain natural standing pose",
            "gaze_change": "look at the product",
            "expression": "gentle smile, natural expression",
            "additional_edits": "enhance natural lighting"
        },
        "background_sounds_prompt": ""
    }


def generate_image_prompts(korean_scene: str, brand: str = "", previous_context: list = None) -> Dict:
    """
    한국어 장면 설명을 영어 이미지 프롬프트로 변환

    Args:
        korean_scene: 한국어 장면 설명 (예: "지지가 침대에 앉아...")
        brand: 브랜드 이름 (예: "이니스프리")
        previous_context: 이전 장면들의 리스트 [{"scene": "...", "dialogue": "..."}, ...]

    Returns:
        {
            "dialogue": "...",
            "narration": "...",
            "t2i_prompt": {...},
            "image_edit_prompt": {...}
        }
    """
    load_prompt_model()

    # 브랜드 정보 추가
    brand_context = f"\nBrand: {brand}" if brand else ""

    # 이전 장면 컨텍스트 구성 (장면 + 발화 포함하여 단어 반복 방지)
    if previous_context and len(previous_context) > 0:
        # 최근 2-3개 장면의 발화를 포함하여 단어 반복 방지
        recent_contexts = previous_context[-2:]  # 최근 2개만
        context_lines = []
        for ctx in recent_contexts:
            if ctx.get('dialogue'):
                context_lines.append(f"Scene: \"{ctx['scene']}\" → Dialogue: \"{ctx['dialogue']}\"")
            else:
                context_lines.append(f"Scene: \"{ctx['scene']}\" → (no dialogue)")
        dialogue_context = "\n" + "\n".join(context_lines)
    else:
        dialogue_context = ""

    full_prompt = f"{PROMPT_SYSTEM_INSTRUCTION}\n{dialogue_context}\nCurrent Scene: {korean_scene}{brand_context}"

    messages = [
        {"role": "user", "content": full_prompt}
    ]

    input_ids = _tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt"
    )

    output = _model.generate(
        input_ids.to(_model.device),
        max_new_tokens=512,  # 더 긴 JSON 출력을 위해
        do_sample=True,
        temperature=0.5,  # 더 일관된 출력
        top_p=0.9,
    )

    # 생성된 텍스트 추출
    generated_ids = output[0][input_ids.shape[1]:]
    generated_text = _tokenizer.decode(generated_ids, skip_special_tokens=True)

    # <think> 태그 제거
    if "<think>" in generated_text:
        parts = generated_text.split("</think>")
        if len(parts) > 1:
            generated_text = parts[1].strip()

    # JSON 추출
    prompts = extract_json_from_text(generated_text)

    return prompts


if __name__ == "__main__":
    # 테스트
    test_scene = "지지가 침대에 앉아 침대 앞에 있는 협탁에 손을 뻗어 이니스프리의 '그린티 밀크 보습 에센스'를 손에 쥠"
    test_brand = "이니스프리"

    print(f"=== 한국어 장면 ===")
    print(test_scene)
    print(f"\n브랜드: {test_brand}")
    print("\n=== 영어 프롬프트 생성 중... ===\n")

    result = generate_image_prompts(test_scene, test_brand)

    print("=== T2I Prompt ===")
    print(json.dumps(result["t2i_prompt"], indent=2, ensure_ascii=False))
    print("\n=== Image Edit Prompt ===")
    print(json.dumps(result["image_edit_prompt"], indent=2, ensure_ascii=False))

