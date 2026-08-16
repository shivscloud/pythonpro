FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/app/.local/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /home/app appuser
WORKDIR /app

# Install Python dependencies first to leverage Docker cache
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app
RUN chown -R appuser:appuser /app

USER appuser
EXPOSE 8080

# Use Gunicorn for production; bind to 0.0.0.0:8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "app:app"]
