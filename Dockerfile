FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates tzdata openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY HGXZ /app/HGXZ
ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
EXPOSE 8080
ENTRYPOINT ["python", "-m", "HGXZ.cli"]
