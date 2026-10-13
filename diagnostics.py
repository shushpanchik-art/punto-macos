#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика punto - проверка разрешений и событий клавиатуры
"""

import sys
import os
import time

print("=" * 60)
print("PUNTO DIAGNOSTICS - Проверка системы")
print("=" * 60)
print()

# 1. Проверка Python
print("1️⃣  Python:")
print(f"   Версия: {sys.version}")
print(f"   Путь: {sys.executable}")
print()

# 2. Проверка библиотек
print("2️⃣  Библиотеки:")
try:
    import pynput
    print(f"   ✅ pynput установлен")
except ImportError:
    print("   ❌ pynput НЕ установлен!")

try:
    import objc
    print("   ✅ pyobjc установлен")
except ImportError:
    print("   ❌ pyobjc НЕ установлен!")

try:
    from AppKit import NSApplication
    print("   ✅ AppKit доступен")
except ImportError:
    print("   ❌ AppKit НЕ доступен!")

print()

# 3. Проверка Accessibility
print("3️⃣  Проверка разрешений Accessibility:")
try:
    from Quartz import AXIsProcessTrusted, AXIsProcessTrustedWithOptions
    from Foundation import NSDictionary

    # Проверяем текущие разрешения
    is_trusted = AXIsProcessTrusted()

    if is_trusted:
        print("   ✅ Accessibility разрешения ЕСТЬ")
    else:
        print("   ❌ Accessibility разрешения ОТСУТСТВУЮТ!")
        print()
        print("   РЕШЕНИЕ:")
        print("   1. Открой: Системные настройки → Конфиденциальность и безопасность")
        print("   2. Найди: Универсальный доступ (Accessibility)")
        print("   3. Добавь: Python или Terminal")
        print("   4. Перезапусти punto")

except Exception as e:
    print(f"   ⚠️  Не удалось проверить: {e}")

print()

# 4. Тест захвата клавиатуры
print("4️⃣  Тест захвата событий клавиатуры (5 секунд):")
print("   Нажми любую клавишу в течение 5 секунд...")
print()

try:
    from pynput import keyboard

    events_captured = []

    def on_press(key):
        events_captured.append(('press', key))
        print(f"   ✅ Захвачено нажатие: {key}")

    def on_release(key):
        events_captured.append(('release', key))
        if len(events_captured) >= 4:  # 2 нажатия + 2 отпускания
            return False  # Останавливаем тест

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # Ждём 5 секунд или пока не будет 4 события
    start = time.time()
    while listener.running and (time.time() - start < 5):
        time.sleep(0.1)

    listener.stop()

    print()
    if events_captured:
        print(f"   ✅ Захвачено {len(events_captured)} событий")
        print("   Punto должен работать!")
    else:
        print("   ❌ НЕ захвачено НИ ОДНОГО события!")
        print("   Проблема: Python не имеет доступа к клавиатуре")
        print()
        print("   РЕШЕНИЕ:")
        print("   1. Выдай разрешения Accessibility (см. выше)")
        print("   2. Убедись, что punto запущен от твоего пользователя")
        print("   3. Проверь логи: ~/punto/punto.err.log")

except Exception as e:
    print(f"   ❌ Ошибка при тестировании: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 60)
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 60)
