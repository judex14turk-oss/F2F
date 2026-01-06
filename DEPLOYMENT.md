# 🚀 Deployment Guide

Полное руководство по настройке автоматического деплоя из GitHub на production сервер.

## 📋 Содержание

- [Обзор](#обзор)
- [Предварительные требования](#предварительные-требования)
- [Настройка SSH](#настройка-ssh)
- [Настройка GitHub Secrets](#настройка-github-secrets)
- [Настройка сервера](#настройка-сервера)
- [Тестирование](#тестирование)
- [Устранение проблем](#устранение-проблем)

---

## 🎯 Обзор

При каждом `git push` в ветку `main`:
1. GitHub Actions автоматически запускается
2. Подключается к серверу по SSH
3. Обновляет код (`git pull`)
4. Устанавливает зависимости (если изменился `requirements.txt`)
5. Перезапускает бота

**Сервер:** `130.49.146.209`  
**Путь:** `/home/app`  
**Репозиторий:** https://github.com/judex14turk-oss/F2F

---

## ✅ Предварительные требования

- [x] Git репозиторий настроен
- [x] GitHub репозиторий создан
- [x] Доступ к серверу по SSH
- [ ] SSH ключ для автоматизации
- [ ] Настроенный метод перезапуска бота

---

## 🔐 Настройка SSH

### 1. Генерация SSH ключа (если нет)

На вашем **локальном компьютере**:

```bash
# Генерируем новый SSH ключ
ssh-keygen -t ed25519 -C "github-actions-deployment" -f ~/.ssh/github_deploy

# Не устанавливайте passphrase (просто нажмите Enter)
```

### 2. Копирование публичного ключа на сервер

```bash
# Посмотрите публичный ключ
cat ~/.ssh/github_deploy.pub

# Скопируйте вывод и добавьте на сервер
ssh root@130.49.146.209

# На сервере:
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
# Вставьте публичный ключ на новую строку
# Сохраните (Ctrl+X, Y, Enter)

# Установите правильные права
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### 3. Тестирование SSH подключения

```bash
# На локальном компьютере
ssh -i ~/.ssh/github_deploy root@130.49.146.209

# Если подключение успешно - все настроено правильно!
```

---

## 🔑 Настройка GitHub Secrets

1. Откройте ваш репозиторий на GitHub
2. Перейдите: **Settings** → **Secrets and variables** → **Actions**
3. Нажмите **New repository secret**

Добавьте следующие секреты:

### `SSH_PRIVATE_KEY`
```bash
# На локальном компьютере получите приватный ключ:
cat ~/.ssh/github_deploy

# Скопируйте ВСЁ содержимое (включая -----BEGIN и -----END)
# Вставьте в GitHub Secret
```

### `SERVER_HOST`
```
130.49.146.209
```

### `SERVER_USER`
```
root
```

---

## ⚙️ Настройка сервера

### 1. Клонирование репозитория на сервер (если еще не сделано)

```bash
ssh root@130.49.146.209

# Если папка /home/app уже существует с кодом - пропустите этот шаг
# Иначе:
cd /home
git clone https://github.com/judex14turk-oss/F2F.git app
cd app
```

### 2. Установка зависимостей

```bash
cd /home/app
pip install -r requirements.txt
```

### 3. Настройка метода перезапуска

Отредактируйте файл `.github/workflows/deploy.yml` и раскомментируйте нужный метод:

#### Вариант A: systemd (рекомендуется для production)

На сервере создайте сервис:

```bash
sudo nano /etc/systemd/system/bot.service
```

Вставьте:

```ini
[Unit]
Description=F2F Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/app
ExecStart=/usr/bin/python3 /home/app/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активируйте:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bot
sudo systemctl start bot
sudo systemctl status bot
```

В `.github/workflows/deploy.yml` раскомментируйте:
```yaml
sudo systemctl restart bot
sudo systemctl status bot --no-pager
```

#### Вариант B: PM2 (Node.js process manager)

```bash
# Установите PM2
npm install -g pm2

# Запустите бота
cd /home/app
pm2 start bot.py --name bot --interpreter python3
pm2 save
pm2 startup
```

В `.github/workflows/deploy.yml` раскомментируйте:
```yaml
pm2 restart bot
pm2 status
```

#### Вариант C: Screen (простой вариант)

```bash
screen -dmS bot python bot.py
```

В `.github/workflows/deploy.yml` раскомментируйте соответствующие строки.

### 4. Сделайте deploy.sh исполняемым (опционально)

```bash
chmod +x /home/app/deploy.sh
```

---

## 🧪 Тестирование

### 1. Локальный тест

```bash
# Внесите небольшое изменение
echo "# Test deployment" >> README.md

# Закоммитьте и отправьте
git add .
git commit -m "Test: автоматический деплой"
git push origin main
```

### 2. Проверка GitHub Actions

1. Откройте ваш репозиторий на GitHub
2. Перейдите на вкладку **Actions**
3. Найдите ваш workflow "Deploy to Production Server"
4. Проверьте, что он выполняется успешно (зеленая галочка)

### 3. Проверка на сервере

```bash
ssh root@130.49.146.209
cd /home/app

# Проверьте последний коммит
git log -1 --oneline

# Проверьте статус бота
# systemd:
sudo systemctl status bot

# PM2:
pm2 status

# Процесс:
ps aux | grep bot.py
```

---

## 🔧 Устранение проблем

### Ошибка: "Permission denied (publickey)"

**Причина:** SSH ключ не настроен или неправильный.

**Решение:**
1. Проверьте, что публичный ключ добавлен в `~/.ssh/authorized_keys` на сервере
2. Проверьте, что приватный ключ точно скопирован в GitHub Secret
3. Убедитесь, что права на папку `.ssh` корректны (700) и на `authorized_keys` (600)

### Ошибка: "Command not found: systemctl/pm2"

**Причина:** Выбранный метод перезапуска не установлен на сервере.

**Решение:**
1. Установите нужный инструмент (systemd, pm2, и т.д.)
2. Или используйте другой метод перезапуска

### Workflow завершается, но бот не перезапускается

**Причина:** Метод перезапуска не раскомментирован в `.github/workflows/deploy.yml`.

**Решение:**
1. Отредактируйте `.github/workflows/deploy.yml`
2. Раскомментируйте строки для вашего метода перезапуска
3. Закоммитьте и отправьте изменения

### Бот не работает после деплоя

**Причина:** Возможно, ошибка в коде или конфигурации.

**Решение:**
1. Проверьте логи на сервере:
   ```bash
   # systemd
   sudo journalctl -u bot -n 50
   
   # PM2
   pm2 logs bot
   
   # Manual
   tail -f /var/log/bot.log
   ```
2. Проверьте переменные окружения (.env файл)
3. Убедитесь, что все зависимости установлены

### Git конфликты на сервере

**Причина:** Изменения на сервере конфликтуют с GitHub.

**Решение:**
```bash
ssh root@130.49.146.209
cd /home/app

# Сбросить все локальные изменения
git fetch origin main
git reset --hard origin/main
```

---

## 📝 Ручной деплой

Если нужно задеплоить вручную:

```bash
ssh root@130.49.146.209
cd /home/app
./deploy.sh
```

Или используйте Git напрямую:

```bash
ssh root@130.49.146.209
cd /home/app
git pull origin main
pip install -r requirements.txt
sudo systemctl restart bot  # или ваш метод перезапуска
```

---

## 🎉 Готово!

Теперь при каждом `git push` в `main` ваш бот будет автоматически обновляться на сервере!

### Следующие шаги:

- [ ] Настройте мониторинг бота
- [ ] Добавьте уведомления о деплое (Telegram, Discord)
- [ ] Настройте логирование
- [ ] Добавьте health checks

---

## 📚 Дополнительные ресурсы

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [SSH Key Authentication](https://www.ssh.com/academy/ssh/key)
- [Systemd Tutorial](https://www.digitalocean.com/community/tutorials/how-to-use-systemctl-to-manage-systemd-services-and-units)
- [PM2 Guide](https://pm2.keymetrics.io/docs/usage/quick-start/)
