# backend/Dockerfile

# 1. Change this line to 3.12
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (ffmpeg is often needed for audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 2. Install dependencies
# Note: Python 3.12 removed 'distutils', so we ensure setuptools is up to date
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r req.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]