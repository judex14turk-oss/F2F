#!/bin/bash
# Этот скрипт запустить ОДИН РАЗ на сервере для настройки автодеплоя

set -e

echo "🚀 Настройка сервера для автоматического деплоя"

# 1. Удалить старую папку и склонировать репо
cd /home
rm -rf /home/app_old
mv /home/app /home/app_old || true
git clone https://github.com/judex14turk-oss/F2F.git app
cd /home/app

# 2. Скопировать .env из старой папки (если есть)
if [ -f /home/app_old/.env ]; then
    cp /home/app_old/.env /home/app/.env
    echo "✅ .env скопирован из старой установки"
fi

# 3. Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Убить старый процесс и запустить новый
pkill -f "python.*main.py" || true
sleep 2
nohup /home/app/venv/bin/python3 /home/app/main.py > /var/log/bot.log 2>&1 &

echo ""
echo "✅ Готово! Теперь при каждом git push origin main бот будет автоматически обновляться"
echo "Проверьте логи: tail -f /var/log/bot.log"
