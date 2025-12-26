FROM python:3.8

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# 시스템 패키지 설치 (ffmpeg, OpenCV 등)
RUN apt-get update && \
    apt-get install -y ffmpeg libsm6 libxext6 libgl1-mesa-glx && \
    apt-get clean

# requirements 설치
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install numpy scipy "librosa==0.9.2" opencv-python opencv-contrib-python torch torchvision torchaudio tqdm soundfile audioread && \
    pip install fastapi uvicorn[standard] python-multipart pydantic

COPY . .

RUN mkdir -p results temp uploads

EXPOSE 2000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "2000"]
