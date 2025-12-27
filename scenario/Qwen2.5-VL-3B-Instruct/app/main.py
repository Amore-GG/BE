# app/main.py
from fastapi import FastAPI, UploadFile, File, Form
from .model_loader import load_model
from PIL import Image
import io

app = FastAPI()

processor = None
model = None

@app.on_event("startup")
def startup():
    global processor, model
    processor, model = load_model()

@app.get("/health")
def health():
    return {"ok": True, "model_loaded": model is not None}

@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    prompt: str = Form(default="이 이미지를 설명해주세요.")
):
    # 이미지 로드
    image_bytes = await image.read()
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # 메시지 구성
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": pil_image},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    
    # 입력 처리
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(
        text=[text],
        images=[pil_image],
        return_tensors="pt",
    ).to(model.device)
    
    # 생성
    outputs = model.generate(**inputs, max_new_tokens=512)
    
    # 디코딩
    generated_ids = outputs[:, inputs.input_ids.shape[1]:]
    result = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    
    return {"result": result}