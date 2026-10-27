FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    requests \
    "psycopg[binary]"

RUN mkdir -p /app/data

COPY database/ /app/database/
COPY shared/ /app/shared/

CMD ["python", "database/seeds/seed_items.py"]