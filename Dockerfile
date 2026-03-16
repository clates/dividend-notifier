FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pandas/numpy
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set timezone
ENV TZ=America/New_York

CMD ["python", "scheduler.py"]
