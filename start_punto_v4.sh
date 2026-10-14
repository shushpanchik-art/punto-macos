#!/bin/bash
# Останавливаем v3 если запущен
pkill -f punto_v3.py

# Запускаем v4
source venv/bin/activate
python3 punto_v4.py
