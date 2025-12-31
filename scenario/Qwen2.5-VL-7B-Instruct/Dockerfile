FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# 시스템 패키지 (Qwen2.5에 맞게 ffmpeg 등 필요 패키지 추가 가능)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 디렉토리 생성 (필요시)
RUN mkdir -p uploads outputs workflows

EXPOSE 3000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "3000"]

