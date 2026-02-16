@echo off
REM Установка зависимостей для AutoScoutBot
REM Использует Python 3.12 из виртуального окружения

echo Проверка виртуального окружения...
if not exist ".venv312\Scripts\python.exe" (
    echo Виртуальное окружение не найдено. Создание нового окружения на Python 3.12...
    py -3.12 -m venv .venv312
    if errorlevel 1 (
        echo ОШИБКА: Не удалось создать виртуальное окружение!
        echo Убедитесь, что Python 3.12 установлен и доступен как py -3.12
        pause
        exit /b 1
    )
    echo Виртуальное окружение создано успешно.
) else (
    echo Виртуальное окружение найдено.
)

echo.
echo Обновление pip...
.venv312\Scripts\python.exe -m pip install --upgrade pip

echo.
echo Установка зависимостей из requirements.txt...
.venv312\Scripts\python.exe -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ОШИБКА: Не удалось установить зависимости!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Установка завершена успешно!
echo ========================================
echo.
echo Теперь вы можете запустить бота командой: run_bot.bat
echo.
pause

