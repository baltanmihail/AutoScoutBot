# AutoScoutBot

Telegram-бот для поиска стартапов по базе Сколково с RAG, Re-ranking (GigaChat) и самообучением.

## Быстрый старт

1. **Клонируйте репозиторий** и установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

2. **Конфигурация** — один из вариантов:
   - Скопируйте `config.example.py` в `config.py` и заполните `TELEGRAM_TOKEN`, `GIGACHAT_API_TOKEN`, `ADMIN_IDS`.
   - Либо создайте файл `.env` в корне с переменными (см. ниже) и не создавайте `config.py` — тогда используется `config_env.py`.

3. Положите в корень файл **SkolkovoStartups.csv** (база Сколково), если его ещё нет.

4. Запуск:
   ```bash
   python bot.py
   ```

## Переменные окружения (.env или Railway)

При отсутствии `config.py` конфигурация берётся из окружения:

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_TOKEN` | Токен бота от @BotFather |
| `GIGACHAT_API_TOKEN` | Токен GigaChat API |
| `ADMIN_IDS` | ID админов через запятую, например `123,456` |
| `SKOLKOVO_DATABASE_PATH` | Путь к CSV (по умолчанию `SkolkovoStartups.csv`) |
| `RAG_ENABLED` | `true` / `false` |
| `RAG_INDEX_FILE`, `RAG_TOP_K` | Опционально |

Пример `.env`:

```env
TELEGRAM_TOKEN=ваш_токен_бота
GIGACHAT_API_TOKEN=ваш_токен_gigachat
ADMIN_IDS=5079636941,1856746424
```

## Документация

Вся документация перенесена в папку **docs/**:

- **[docs/README.md](docs/README.md)** — оглавление документации
- **[docs/START_HERE.md](docs/START_HERE.md)** — с чего начать, обзор системы
- **[docs/FULL_EXPLANATION.md](docs/FULL_EXPLANATION.md)** — как устроены RAG, Re-ranking, Few-shot, FAQ
- **[docs/README_MONITORING.md](docs/README_MONITORING.md)** — мониторинг и аналитика
- **[docs/CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md)** — настройки и админ-панель
- **[docs/INTERACTIVE_ACTIONS.md](docs/INTERACTIVE_ACTIONS.md)** — интерактивные действия после поиска
- **[docs/ai_learning.md](docs/ai_learning.md)** — самообучение (AI Learning)
- **[docs/DEPLOY_RAILWAY.md](docs/DEPLOY_RAILWAY.md)** — деплой на Railway

## Деплой на Railway

1. Запушьте проект в GitHub.
2. В [Railway](https://railway.app): New Project → Deploy from GitHub repo.
3. В настройках сервиса задайте **Variables**: `TELEGRAM_TOKEN`, `GIGACHAT_API_TOKEN`, `ADMIN_IDS`.
4. Тип сервиса: **Worker**. В репозитории уже есть **Procfile**: `worker: python bot.py`.

Подробнее: **[docs/DEPLOY_RAILWAY.md](docs/DEPLOY_RAILWAY.md)**.

Если в корне остались старые файлы документации (`START_HERE.md`, `CONFIG_GUIDE.md`, `FULL_EXPLANATION.md`, `README_MONITORING.md`, `INTERACTIVE_ACTIONS.md`), их можно удалить — актуальная версия в `docs/`.

## Структура проекта

```
AutoScoutBot/
├── bot.py                 # Точка входа
├── config.example.py      # Пример конфигурации
├── config_env.py          # Конфиг из переменных окружения
├── Procfile               # Для Railway (worker)
├── requirements.txt
├── docs/                  # Вся документация
├── handlers/
├── services/
├── ai_learning/
├── data/, domain/, utils/
└── ...
```
