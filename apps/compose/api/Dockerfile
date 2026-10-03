FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/compose/api/requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser apps/compose/api/app.py .

USER appuser

EXPOSE 8000

CMD ["python", "app.py"]
