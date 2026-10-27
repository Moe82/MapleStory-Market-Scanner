
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    google-genai \
    pydantic \
    "psycopg[binary]"

COPY services/analyzer/ .
COPY database/ /app/database/
COPY shared/ /app/shared/

CMD ["python", "-u", "main.py"]
