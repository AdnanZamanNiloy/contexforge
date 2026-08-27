FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# faiss-cpu / sentence-transformers wheels need a C toolchain to build here.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        && rm -rf /var/lib/apt/lists/*

# Install dependencies first so they layer-cache independent of source changes.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Application code. Data dirs (data/, uploads, repo_analysis) are created at
# runtime under /app/data and should be mounted as a named volume.
COPY app ./app
COPY core ./core
COPY observability ./observability
COPY __init__.py ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
