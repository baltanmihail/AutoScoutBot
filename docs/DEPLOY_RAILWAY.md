# Деплой AutoScoutBot на Railway

## Подготовка репозитория

1. **Инициализация Git** (если ещё не сделано):
   ```bash
   git init
   git add .
   git commit -m "Деплой 2"
   ```

2. **Убедитесь, что в репозиторий не попадают:**
   - `config.py` с секретами (он в .gitignore)
   - `.env` (в .gitignore)
   - `*.db`, `rag_index_gigachat.json`, `SkolkovoStartups.csv` — при необходимости добавьте в .gitignore или храните CSV в репо, если он не секретный

3. **Пуш в GitHub:**
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/AutoScoutBot.git
   git branch -M main
   git push -u origin main
   ```

## Настройка Railway

1. Зайдите на [railway.app](https://railway.app), войдите через GitHub.

2. **New Project** → **Deploy from GitHub repo** → выберите репозиторий AutoScoutBot.

3. **Variables** (переменные окружения) — обязательно задайте:
   - `TELEGRAM_TOKEN` — токен бота от @BotFather
   - `GIGACHAT_API_TOKEN` — токен GigaChat API  
   - `ADMIN_IDS` — ID админов через запятую: `5079636941,1856746424` (формат `[5079636941, 1856746424]` тоже поддерживается)

   Опционально:
   - `SKOLKOVO_DATABASE_PATH` (по умолчанию `SkolkovoStartups.csv`)
   - `RAG_ENABLED` = `true` / `false`
   - `RAG_INDEX_FILE`, `RAG_TOP_K`

4. **Тип сервиса:** Worker (не Web). В Railway при деплое из репо по умолчанию подхватывается **Procfile**: команда `worker: python bot.py` запускает бота как воркер.

5. **Файлы данных:**  
   - `SkolkovoStartups.csv` должен быть в репозитории или загружаться при старте (например, из внешнего хранилища).  
   - RAG-индекс при первом запуске может строиться 5–10 минут; для ускорения можно собрать индекс локально и положить `rag_index_gigachat.json` в репо (если не в .gitignore) или на объёмное хранилище Railway.

6. После деплоя смотрите логи в Railway — бот должен вывести что-то вроде «Бот запускается...» и «База Сколково загружена».

## Локальная разработка с .env

Создайте в корне проекта файл `.env` (он не коммитится):

```env
TELEGRAM_TOKEN=ваш_токен_бота
GIGACHAT_API_TOKEN=ваш_токен_gigachat
ADMIN_IDS=5079636941,1856746424
```

Не создавайте `config.py` — тогда при запуске `python bot.py` будет использоваться `config_env.py` и переменные из `.env`.

Если хотите по-прежнему использовать локальный `config.py` с секретами — просто оставьте его; тогда он будет подхвачен первым и переменные окружения не нужны.

## Запуск с ПК (локально)

Чтобы запускать бота с компьютера, когда потребуется:

1. **Вариант с config.py**  
   Оставьте в корне проекта свой `config.py` (он в .gitignore, в репозиторий не попадёт). Запуск:
   ```bash
   python bot.py
   ```
   Бот сначала подхватит `config.py`, переменные окружения не нужны.

2. **Вариант без config.py**  
   Создайте в корне `.env` с теми же переменными (TELEGRAM_TOKEN, GIGACHAT_API_TOKEN, ADMIN_IDS и т.д.) и запускайте `python bot.py` — настройки возьмутся из `config_env.py` и `.env`.

Один и тот же репозиторий можно и деплоить на Railway (через Variables), и запускать локально (через config.py или .env).
