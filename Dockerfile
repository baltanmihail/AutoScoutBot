FROM python:3.12-slim

# System deps for LightGBM (libgomp) and general use
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgomp1 \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Run bot
CMD ["python", "bot.py"]
