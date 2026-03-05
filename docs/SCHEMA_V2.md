# Расширенная схема данных (v2)

Схема совместима с базой Сколково (CSV/поля стартапов) и расширяема под внешние источники.

---

## Бот: SQLite `users.db` → таблица `external_startups`

Используется при `/check` и в `scoring/retrain.py` для дообучения по внешним стартапам.

| Колонка | Тип | Описание |
|--------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| inn | TEXT UNIQUE | ИНН компании |
| ogrn | TEXT | ОГРН |
| name | TEXT | Название (из EGRUL/Checko/BFO) |
| full_legal_name | TEXT | Полное наименование |
| region | TEXT | Регион |
| status_egrul | TEXT | Статус из ЕГРЮЛ |
| registration_date | TEXT | Дата регистрации |
| features_json | TEXT | Фичи для ML (JSON), извлекаются парсерами |
| features_filled_count | INTEGER | Количество заполненных полей |
| ml_overall | REAL | Общий ML-скор (XGBoost) |
| raw_data_json | TEXT | Сырые данные всех источников (checko, egrul, bfo, news, moex) |
| **ratios_json** | TEXT | Расчётные коэффициенты: `{ "latest_year", "static", "dynamic" }` — ликвидность, Z-Альтман, Z-Таффлер, динамика и т.д. |
| created_at, updated_at | TIMESTAMP | Время создания/обновления |

- **static** — коэффициенты за последний год (current_ratio, quick_ratio, altman_z, roe, roa и др.).
- **dynamic** — YoY, CAGR, years_with_revenue, profit_trend и т.д.

---

## Backend (PostgreSQL): модели

- **startups** — стартапы из Сколково (миграция из CSV).
- **startup_financials** — финансы по годам (revenue, profit).
- **external_data** — кэш внешних источников (source, data_json).
- **external_startups** (Backend) — внешние стартапы с ML-полями (inn, name, features_json, ml_*).
- **raw_external_data** — сырые ответы по каждому источнику для external_startup.

Совместимость: бот пишет в свою SQLite `external_startups`; при необходимости данные можно выгружать в backend или в JSONL для retrain.

---

## Источники данных (парсеры)

| Источник | Данные |
|----------|--------|
| Checko API /finances | БФО по годам, название, ОГРН, дата рег., статус, ОКВЭД, адрес |
| Checko API /company | Детали: капитал, руководители, учредители, ОКВЭД (сохраняются в raw_data / company_details) |
| EGRUL | Название, ОГРН, дата, статус, адрес |
| BFO (ФНС) | БФО при доступности (часто 403) |
| News | Упоминания в СМИ, тональность |
| MOEX | Бумаги по ИНН |

Объединение финансов: Checko + BFO через один и тот же набор кодов строк БФО; при расчёте коэффициентов используется объединённый словарь по годам.
