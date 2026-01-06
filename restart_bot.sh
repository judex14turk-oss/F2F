#!/bin/bash
# Надежный скрипт перезапуска бота

echo "🛑 Останавливаем все процессы бота..."

# Убиваем все python процессы несколько раз для надежности
sudo killall -9 python3 2>/dev/null
sleep 2
sudo killall -9 python 2>/dev/null
sleep 2
pkill -9 -f main.py 2>/dev/null
sleep 3

# Проверяем, что всё убито
REMAINING=$(ps aux | grep -E "python.*main.py" | grep -v grep | wc -l)
if [ $REMAINING -gt 0 ]; then
    echo "⚠️ Остались процессы, убиваем по PID..."
    ps aux | grep -E "python.*main.py" | grep -v grep | awk '{print $2}' | xargs -r sudo kill -9
    sleep 3
fi

echo "✅ Все процессы остановлены"
echo ""
echo "🚀 Запускаем бота..."

cd /home/app
nohup /home/app/venv/bin/python3 /home/app/main.py > /var/log/bot.log 2>&1 &

echo "⏳ Ждем 5 секунд..."
sleep 5

# Проверяем, запустился ли
if pgrep -f "python.*main.py" > /dev/null; then
    echo "✅ Бот запущен успешно!"
    echo "📊 PID: $(pgrep -f 'python.*main.py')"
    echo "📝 Логи: tail -f /var/log/bot.log"
else
    echo "❌ Бот не запустился, проверьте логи:"
    tail -20 /var/log/bot.log
    exit 1
fi
