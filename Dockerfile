# Last verified: 2026-04-16 — python:3.12.3-slim (pin digest in production CI)
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b7533cf962061d95524c64c045809

WORKDIR /app/src
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY VERSION /app/VERSION
COPY src/ /app/src/

EXPOSE 8765
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]
