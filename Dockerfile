FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg gcc g++ make pkg-config libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel && pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data/downloads /app/data/thumbnails
ENV BOT_TOKEN=replace_me ADMIN_IDS=123456789 DATABASE_URL=sqlite+aiosqlite:////tmp/bot.db REDIS_URL=redis://localhost:6379/0 LOG_LEVEL=INFO
CMD ["python", "main.py"]
