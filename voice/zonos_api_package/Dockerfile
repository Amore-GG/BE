FROM python:3.10-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# 빌드 패키지 + Rust + libsndfile (wav 로드용)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        libsndfile1 && \
    curl https://sh.rustup.rs -sSf | sh -s -- -y && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements_api.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements_api.txt

COPY . .
EXPOSE 1000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "1000"]
