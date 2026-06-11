FROM python:3.11-slim

WORKDIR /app

# Dépendances système : Xvfb (virtual display pour Playwright headless=False)
# + libs nécessaires à Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        libglib2.0-0 \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch d'abord — évite de puller les wheels CUDA (~2 GB)
RUN pip install --no-cache-dir "torch>=2.1.0" --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn \
 && playwright install chromium

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
     "--timeout", "300", \
     "--keep-alive", "5", \
     "--access-logfile", "-"]
