param (
    [string]$commitMessage = "Auto update from local"
)

Write-Host "🚀 Начинаем процесс деплоя проекта на сервер..." -ForegroundColor Cyan

Write-Host "`n📦 1. Сохраняем изменения в Git и отправляем на GitHub..." -ForegroundColor Yellow
git add .
git commit -m $commitMessage
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️ Внимание: git push завершился с ошибкой (возможно, нет новых изменений или конфликт)." -ForegroundColor Red
    # Не прерываем выполнение, возможно мы просто хотим перезапустить контейнеры на сервере
}

Write-Host "`n🌐 2. Подключаемся к серверу (37.230.192.5) и обновляем контейнеры..." -ForegroundColor Yellow
# Команда для SSH. Если ты используешь специфичный ключ, можно добавить -i путь_к_ключу
$sshCommand = "cd /home/autoscoutbot/autoscoutbot && git pull && sudo docker compose up -d --build"

# Выполняем команду на сервере
ssh autoscoutbot@37.230.192.5 $sshCommand

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Деплой успешно завершен! Код на сервере обновлен и запущен." -ForegroundColor Green
} else {
    Write-Host "`n❌ Произошла ошибка при выполнении команд на сервере." -ForegroundColor Red
}
