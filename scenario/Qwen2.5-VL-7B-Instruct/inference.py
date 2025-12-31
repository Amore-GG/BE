import torch
from transformers import AutoModelForVision2Seq, AutoProcessor
from PIL import Image
import os

print("[INFO] Starting Qwen2.5-VL-7B-Instruct inference script...")

def load_resize(path, max_side=512):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((int(w*scale), int(h*scale)))
    return img

# Set model directory
model_dir = os.path.dirname(os.path.abspath(__file__))
print(f"[INFO] Model directory: {model_dir}")

# Device selection (macOS: MPS, else CUDA/CPU)
device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
dtype = torch.float16 if device in ["cuda", "mps"] else torch.float32
print(f"[INFO] Using device: {device}, dtype: {dtype}")

# Load model and processor
print("[INFO] Loading model...")
model = AutoModelForVision2Seq.from_pretrained(
    model_dir,
    dtype=dtype,  # torch_dtype deprecated, use dtype
).to(device).eval()
print("[INFO] Model loaded.")
print("[INFO] Loading processor...")
processor = AutoProcessor.from_pretrained(model_dir, use_fast=True)
print("[INFO] Processor loaded.")

# Image paths (edit as needed)
gigi_path = os.path.join(model_dir, "gigi(1).png")
prod_path = os.path.join(model_dir, "laneige.jpg")

print(f"[INFO] Loading images: {gigi_path}, {prod_path}")
gigi_img = load_resize(gigi_path, 512) if os.path.exists(gigi_path) else None
prod_img = load_resize(prod_path, 512) if os.path.exists(prod_path) else None
print(f"[INFO] gigi_img loaded: {gigi_img is not None}, prod_img loaded: {prod_img is not None}")

messages = [
    {
        "role": "user",
        "content": [
            *( [{"type": "image", "image": gigi_img}] if gigi_img else [] ),
            *( [{"type": "image", "image": prod_img}] if prod_img else [] ),
            {"type": "text", "text": "Make a 30-second ad scenario script in Korean not a timetable but a scenario script."}
        ],
    }
]

print("[INFO] Applying chat template...")
text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
print("[INFO] Chat template applied.")

# 이미지 입력만 추출
image_inputs = [item["image"] for msg in messages for item in msg["content"] if item["type"] == "image"]
print(f"[INFO] Number of image inputs: {len(image_inputs)}")

print("[INFO] Preparing processor inputs...")
inputs = processor(
    text=[text],
    images=image_inputs,
    padding=True,
    return_tensors="pt"
).to(device)
print("[INFO] Inputs prepared.")

print("[INFO] Running inference...")
with torch.no_grad():
    generated_ids = model.generate(
        **inputs,
        max_new_tokens=256,
        do_sample=True,
        temperature=0.7,
    )
print("[INFO] Inference complete.")

output = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
print("\n===== Generated Scenario =====\n")
print(output)
