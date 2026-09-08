#!/usr/bin/env bash
set -e

echo "=== Встановлення Freelance AI Helper на VPS ==="

# Визначення поточної папки
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Папка проєкту: $PROJECT_DIR"

# Перевірка Python 3
if ! command -v python3 &> /dev/null; then
    echo "Помилка: Python 3 не встановлено. Встановіть через 'apt update && apt install -y python3 python3-venv python3-pip' (або pacman / dnf)."
    exit 1
fi

# Створення venv
if [ ! -d "venv" ]; then
    echo "Створюю virtual environment..."
    python3 -m venv venv
fi

echo "Оновлення pip та встановлення залежностей..."
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt

# Перевірка .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Створюю .env з .env.example..."
        cp .env.example .env
        echo "УВАГА: Заповніть ваші токени у файлі .env!"
    fi
fi


# Створення директорій data та logs
mkdir -p data logs

# Перевірка синтаксису
echo "Перевірка працездатності..."
./venv/bin/python -m compileall freelance_helper
./venv/bin/python scripts/check_project_logic.py

echo ""
echo "=== Налаштування завершено успішно! ==="
echo "Для ручного запуску: ./venv/bin/python -m freelance_helper.app.main"
echo "Для встановлення systemd сервісу:"
echo "1. Відредагуйте deploy/freelance-helper.service (перевірте WorkingDirectory та ExecStart)."
echo "2. sudo cp deploy/freelance-helper.service /etc/systemd/system/"
echo "3. sudo systemctl daemon-reload"
echo "4. sudo systemctl enable --now freelance-helper"
echo "5. sudo systemctl status freelance-helper"
