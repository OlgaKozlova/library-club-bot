# Деплой Telegram-бота (VPS + systemd)

Документ описывает полный процесс деплоя бота на сервер Ubuntu/Debian с использованием systemd.
Все команды выполняются от имени пользователя с sudo-доступом.

## 1. Подготовка сервера

Обновить систему и установить необходимые пакеты:

```
$ sudo apt update && sudo apt -y upgrade  
$ sudo apt -y install git python3 python3-venv python3-pip
```

Создать каталоги под приложение и базу данных:

```
$ sudo mkdir -p /opt/library-club-bot  
$ sudo mkdir -p /var/lib/library-club-bot  
$ sudo chown -R $USER:$USER /opt/library-club-bot  
$ sudo chown -R $USER:$USER /var/lib/library-club-bot
```


## 2. Клонирование репозитория
```
$ cd /opt/library-club-bot  
$ git clone https://github.com/OlgaKozlova/library-club-bot.git .
```

## 3. Виртуальное окружение и зависимости

```
$ python3 -m venv venv  
$ source venv/bin/activate  
$ pip install -U pip  
$ pip install -r requirements.txt
```

Все зависимости устанавливаются строго внутри виртуального окружения.

## 4. Переменные окружения

Создать файл окружения (не хранится в git):

```
$ nano /opt/library-club-bot/.env
```

Пример содержимого файла .env:

```
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN  
TZ=Europe/Moscow  
VISIT_ASK_HOUR=20  
DB_PATH=/var/lib/library-club-bot/bot.sqlite3
```

Задать безопасные права:

```
$ chmod 600 /opt/library-club-bot/.env
```

## 5. systemd service

Создать unit-файл сервиса:

```
$ sudo nano /etc/systemd/system/library-club-bot.service
```

Содержимое файла:
```
[Unit]  
Description=Library Club Bot  
After=network-online.target  
Wants=network-online.target  

[Service]  
Type=simple  
WorkingDirectory=/opt/library-club-bot  
EnvironmentFile=/opt/library-club-bot/.env  
ExecStart=/opt/library-club-bot/venv/bin/python /opt/library-club-bot/main.py  
Restart=always  
RestartSec=3  
PYTHONUNBUFFERED=1  

[Install]  
WantedBy=multi-user.target  
```

## 6. Активация и запуск сервиса

```
$ sudo systemctl daemon-reload  
$ sudo systemctl enable library-club-bot  
$ sudo systemctl start library-club-bot  
```

Проверка статуса сервиса:
```
$ sudo systemctl status library-club-bot
```

## 7. Логи и обслуживание

Просмотр логов:
```
$ sudo journalctl -u library-club-bot -f
```
Перезапуск сервиса:
```
$ sudo systemctl restart library-club-bot
```
Обновление кода:
```
$ cd /opt/library-club-bot  
$ git pull  
$ source venv/bin/activate  
$ pip install -r requirements.txt  
$ sudo systemctl restart library-club-bot
```

Готово. Бот запущен как системный сервис и автоматически стартует при перезагрузке сервера.
