FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch d'abord — évite de puller les wheels CUDA (~2 GB)
RUN pip install --no-cache-dir "torch>=2.1.0" --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Dossiers persistants (écrasés par les volumes au runtime)
RUN mkdir -p static/uploads/thumbs static/uploads/outfits logs data

ENV PYTHONUNBUFFERED=1 \
    PORT=5001 \
    HF_HOME=/app/data/hf_cache \
    HF_HUB_OFFLINE=0

EXPOSE 5001

CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:5001", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-"]
