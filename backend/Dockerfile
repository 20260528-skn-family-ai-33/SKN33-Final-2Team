# GrowPath 5차 목업 · 앱 이미지 (FastAPI + 화면)
# AWS(ECS·App Runner 등)에 올릴 때도 이 이미지를 그대로 쓰고, 설정은 환경변수(DATABASE_URL·키)로만 넣는다.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
WORKDIR /srv/growpath
COPY requirements.txt ./
COPY database/requirements.txt database/requirements-db.txt ./database/
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/web ./web
COPY backend/db ./db
COPY backend/tools ./tools
RUN python tools/install_catalog_tokenizer.py
EXPOSE 8785
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8785"]
