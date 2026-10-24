FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    'streamlink>=7,<9' \
    'opencv-python-headless>=4.9,<5' \
    'numpy>=1.26,<3' \
    google-genai \
    pydantic
    
WORKDIR /app

COPY services/capture/ .
COPY shared/ /app/shared/

CMD ["python", "-u", "main.py"]