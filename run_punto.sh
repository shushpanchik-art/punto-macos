#!/bin/bash
# Запускает punto без иконки в доке
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
# Запускаем Python с флагом, скрывающим приложение из дока
exec ./venv/bin/python -c "
import os
import sys
# Скрываем приложение из дока
try:
    from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)
except ImportError:
    pass

# Запускаем основной скрипт
exec(open('punto.py').read())
"
