@echo off
REM Запуск бота AutoScoutBot
REM Использует Python 3.12 из виртуального окружения

if not exist ".venv312\Scripts\python.exe" (
    echo ОШИБКА: Виртуальное окружение не найдено!
    echo Сначала запустите install_deps.bat для установки зависимостей
    pause
    exit /b 1
)

echo Запуск бота...
.venv312\Scripts\python.exe bot.py

if errorlevel 1 (
    echo.
    echo Бот завершил работу с ошибкой.
    pause
    exit /b 1
)

