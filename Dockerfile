FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY prompts/ ./prompts/

ENV PYTHONPATH=/app/src

ENTRYPOINT ["python", "/app/src/main.py"]
