# agora-core — FastAPI 오케스트레이터
# aarch64(dgx-12) 에서 빌드된다. python:3.12-slim 은 arm64 매니페스트가 있다.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

WORKDIR /app

# git 은 BRIEF §15-5(repo 조작은 반드시 git 커밋과 함께) 때문에 필요하다.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 — 소스가 바뀌어도 이 레이어는 캐시된다 (오프라인 재빌드 대비)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
