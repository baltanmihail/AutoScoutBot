FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# torch без CUDA: сборка для видеокарт весит несколько гигабайт, а модель поиска работает на процессоре.
# Ставим его до requirements, чтобы sentence-transformers не подтянул версию с CUDA.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
# Папка проекта подключена в контейнер, поэтому скачанная модель эмбеддингов переживает перезапуски и выкладки
ENV HF_HOME=/app/.cache/huggingface
