# 🚀 AutoScoutBot: Единая База Знаний (WIKI)

Этот документ объединяет все разрозненные инструкции по проекту: план развития, архитектуру, деплой на сервер (СберCloud / Ubuntu) и управление ML-моделями.

---

## 1. 🌟 Концепция и Web-Платформа (SaaS)

AutoScoutBot трансформируется из Telegram-инструмента в полноценную Web-платформу (Product Radar) для инвесторов и стартапов. 

**Роли:**

- **Инвесторы:** Поиск, ML-скоринг (TRL, CRL), финансовое моделирование (IRR, NPV, ROI).
- **Фаундеры:** Загрузка Pitch Deck, верификация через ИНН.

**Ключевая фича:** ИИ-кроссчекинг загруженных фаундером презентаций с суровыми официальными данными (БФО/ЕГРЮЛ через Checko) для поиска "красных флагов" и противоречий.

---

## 2. 💻 Быстрый старт (Разработка)

### Локальный запуск

1. Установите зависимости: `pip install -r requirements.txt`
2. Заполните `.env` (токены Telegram, Yandex/Anthropic, Checko).
3. **Запуск Web-сервера (FastAPI + Сайт):** `python railway_start.py --web` (сайт откроется на `http://localhost:8000`)
4. **Запуск Telegram-бота:** `python railway_start.py --bot`

### Обучение ML-модели

Модели XGBoost обучаются на данных Фонда "Сколково" (5000+ стартапов).

```bash
python run_train.py
```

Это переобучит 6 регрессионных моделей (Overall, TRL, MRL, Финансы и т.д.) и сохранит их в `scoring/models/`. Метрики качества (CV) пишутся в `training_summary.json`.

---

## 3. 🚀 Деплой на VPS (Ubuntu 24.04 / СберCloud)

**Данные сервера:**

- IP: `37.230.192.5`
- Внутренний IP: `192.168.0.4`
- Логин: `autoscoutbot` (изначально был `user1`)
- Пароль: `90281104Mb!.`
- Ключ SSH: файл `id_rsa` в корне проекта

### Вход на сервер (варианты подключения)

**Вариант 1: Быстрый и безопасный вход по ключу (Рекомендуется)**

```bash
ssh -i id_rsa autoscoutbot@37.230.192.5
```

**Вариант 2: Вход по паролю**

```bash
ssh autoscoutbot@37.230.192.5
# пароль: 90281104Mb!.
```

### Настройка сети (постоянный IP)

Если вы пересоздавали сетевой интерфейс, нужно прописать его в Netplan (иначе сеть пропадет после ребута):

```bash
# 1. Создаем конфиг
sudo nano /etc/netplan/01-netcfg.yaml
```

Вставляем туда:
```yaml
network:
  version: 2
  ethernets:
    enp3s0:
      dhcp4: false
      addresses:
        - 192.168.0.4/24
      routes:
        - to: default
          via: 192.168.0.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
```

```bash
# 2. Применяем настройки
sudo netplan apply
```

### Установка ПО (Docker, Nginx, и т.д.)

```bash
# 1. Подключаемся к серверу (см. варианты выше)

# 2. Устанавливаем Docker, Nginx, Certbot
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose git nginx certbot python3-certbot-nginx

# 3. Клонируем проект
mkdir -p ~/autoscoutbot && cd ~/autoscoutbot
git clone <URL_РЕПОЗИТОРИЯ> .

# 4. Настраиваем конфиг
cp .env.example .env
nano .env  # Вписываем TELEGRAM_BOT_TOKEN и ключи API
```

### Запуск через Docker

```bash
docker-compose up -d --build
```

*Запустятся 3 контейнера: База данных (PostgreSQL + pgvector), Бэкенд (Сайт/API) и Telegram-бот.*

### Настройка Домена (autoscoutbot.ru)

```bash
# 1. Создаем конфиг Nginx
sudo nano /etc/nginx/sites-available/autoscoutbot
```

Вставляем:

```nginx
server {
    listen 80;
    server_name autoscoutbot.ru www.autoscoutbot.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# 2. Включаем сайт и SSL
sudo ln -s /etc/nginx/sites-available/autoscoutbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d autoscoutbot.ru -d www.autoscoutbot.ru
```

### Обновление проекта (Деплой новых версий)

Сделай скрипт `deploy.sh` для быстрого апдейта:

```bash
cd ~/autoscoutbot
git pull origin main
docker-compose build
docker-compose up -d
```

---

## 4. 🗄 Структура Базы Данных (V2)

База PostgreSQL. Основные сущности:

- `WebUser` — пользователи сайта (SaaS) с ролями `investor` / `startup`.
- `User` — пользователи Telegram-бота (старая схема).
- `Startup` — стартапы из датасета Сколково (Ground Truth).
- `ExternalStartup` — стартапы, найденные по ИНН через бота/сайт.
- Сущности данных: `RawExternalData` (сырой JSON из ФНС), `StartupFinancial` (финансы по годам), `StartupScore` (ML-оценки).

---

## 5. 🛠 План развития (Roadmap)

1. **Frontend + Auth:** Доделать JWT-авторизацию для WebUser (в `auth.py`).
2. **Личный кабинет Инвестора:** Добавить графики IRR, NPV, ROI и вывод SHAP-моделей (Waterfall-диаграммы).
3. **LLM Deep-Анализ:** Интеграция парсинга презентаций стартапов без БФО (СберЮнити).
4. **Конкурентное позиционирование:** Интеграция киллер-фич против Pelican / Tamara.

