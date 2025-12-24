FROM python:3.10

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Rust 및 빌드 도구 설치
RUN apt-get update && \
    apt-get install -y curl build-essential && \
    curl https://sh.rustup.rs -sSf | sh -s -- -y && \
    apt-get clean

ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements_api.txt ./
RUN pip install --upgrade pip && pip install -r requirements_api.txt

COPY . .

EXPOSE 1000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "1000"]