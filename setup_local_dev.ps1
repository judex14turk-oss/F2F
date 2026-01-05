# Проверка установки ngrok
if (Get-Command "ngrok" -ErrorAction SilentlyContinue) {
    Write-Host "✅ ngrok установлен." -ForegroundColor Green
} else {
    Write-Host "❌ ngrok НЕ установлен или не найден в PATH." -ForegroundColor Red
    Write-Host "Пожалуйста, скачайте и установите ngrok с сайта: https://ngrok.com/download"
    Write-Host "Убедитесь, что при установке вы добавили его в PATH."
    exit
}

# Инструкция для пользователя
Write-Host "`nНастройка локального окружения:" -ForegroundColor Cyan
Write-Host "1. Откройте ОТДЕЛЬНОЕ окно терминала (PowerShell) и запустите команду для создания туннеля:"
Write-Host "   ngrok http 5000" -ForegroundColor Yellow
Write-Host "`n2. В том окне появится строка 'Forwarding'. Скопируйте ссылку, которая выглядит как https://....ngrok-free.app"
Write-Host "3. В ЭТОМ терминале выполните команду (замените ссылку на свою):"
Write-Host "   `$env:WEBAPP_URL='https://ваша-ссылка.ngrok-free.app'" -ForegroundColor Yellow
Write-Host "   python bot.py" -ForegroundColor Yellow
Write-Host "`n4. Откройте ЕЩЕ ОДНО окно терминала, снова установите переменную и запустите веб-сервер:"
Write-Host "   `$env:WEBAPP_URL='https://ваша-ссылка.ngrok-free.app'" -ForegroundColor Yellow
Write-Host "   python app.py" -ForegroundColor Yellow
