import os
import torch
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen2.5-VL-3B-Instruct")

HF_HOME = os.getenv("HF_HOME", "/models/hf")

def load_model():
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float32,
        device_map="cpu",
        low_cpu_mem_usage=True
    )
    return processor, model