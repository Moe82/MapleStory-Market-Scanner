FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir "psycopg[binary]"
RUN pip install --no-cache-dir rapidfuzz
RUN pip install --no-cache-dir rank-bm25
RUN pip install google-genai

COPY services/resolver/ .
COPY database/ /app/database/
COPY shared/ /app/shared/

CMD ["python", "-u", "main.py"]