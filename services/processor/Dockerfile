
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    libgl1 && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    paddlepaddle==3.2.0 \
    -i https://www.paddlepaddle.org.cn/packages/stable/cpu/


COPY services/processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY services/processor/ .
COPY screenshots/ /app/screenshots/
COPY data/ /app/data/
COPY database/ /app/database/
COPY shared/ /app/shared/

# TODO: Remove later
RUN pip install --no-cache-dir debugpy

CMD ["python", "main.py"]
