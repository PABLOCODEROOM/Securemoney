FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application
COPY . .

# Environment defaults (override with .env in production)
ENV FLASK_ENV=production
ENV FLASK_APP=wsgi:app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/auth/login')" || exit 1

# Run gunicorn with 4 workers, 2 threads each
CMD ["gunicorn", "--workers=4", "--threads=2", "--worker-class=gthread", \
     "--bind=0.0.0.0:8000", "--timeout=30", "--access-logfile=-", \
     "--error-logfile=-", "wsgi:app"]
