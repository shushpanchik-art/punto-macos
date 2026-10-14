#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест punto_v3 - качество и скорость
"""

import sys
import os
import time
import importlib.util
from statistics import mean

PUNTO_DIR = os.path.expanduser("~/punto")
sys.path.insert(0, PUNTO_DIR)

def load_module(filename):
    spec = importlib.util.spec_from_file_location("punto", os.path.join(PUNTO_DIR, filename))
    punto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(punto)
    return punto

# Тестовые слова из твоего сообщения
TEST_WORDS = [
    ("еуые", "en", "test"),
    ("цщклы", "en", "work"),
    ("crfxfpfnm", "ru", "сказать"),
    ("ерфе", "en", "that"),
    ("рщцуферук", "en", "however"),
    ("тще", "en", "too"),
    ("[jhjij", "ru", "хорошо"),
    ("crjhjcnm", "ru", "скорость"),
    ("hf,jns", "ru", "работы"),
    ("jcnfkztn", "ru", "остаётся"),
    (";tkfnm", "ru", "желать"),
    ("kexituj", "ru", "лучшего"),
]

print("\n" + "="*70)
print("ТЕСТ PUNTO V3 - КАЧЕСТВО И ПРОИЗВОДИТЕЛЬНОСТЬ")
print("="*70 + "\n")

print("📊 Загрузка punto_v3.py...")
punto = load_module("punto_v3.py")

# Тест качества
print("\n" + "─"*70)
print("ТЕСТ КАЧЕСТВА")
print("─"*70 + "\n")

passed = 0
for wrong, lang, correct in TEST_WORDS:
    result = punto.decide(wrong)
    if result == lang:
        print(f"✅ '{wrong}' → {lang}")
        passed += 1
    else:
        print(f"❌ '{wrong}' → {result} (ожидалось {lang})")

quality = passed / len(TEST_WORDS) * 100
print(f"\nКачество: {passed}/{len(TEST_WORDS)} = {quality:.1f}%")

# Тест производительности
print("\n" + "─"*70)
print("ТЕСТ ПРОИЗВОДИТЕЛЬНОСТИ")
print("─"*70 + "\n")

words_for_bench = [w[0] for w in TEST_WORDS]
times = []

for word in words_for_bench:
    word_times = []
    for _ in range(50):
        start = time.perf_counter()
        punto.decide(word)
        end = time.perf_counter()
        word_times.append((end - start) * 1000)
    times.extend(word_times)

avg_time = mean(times)
print(f"Среднее время: {avg_time:.4f} ms")

# Итоговое сравнение
print("\n" + "="*70)
print("СРАВНЕНИЕ ВЕРСИЙ")
print("="*70)
print()
print("                    Качество    Скорость")
print("─"*70)
print(f"punto.py            58.3%       0.002 ms  (базовая)")
print(f"punto_v2.py         100.0%      23.432 ms (медленно!)")
print(f"punto_v3.py         {quality:5.1f}%      {avg_time:5.3f} ms  (оптимизировано)")
print()

# Оценка
if quality >= 90 and avg_time < 1.0:
    print("✅ ОТЛИЧНО! Качество >90% и скорость <1ms")
elif quality >= 90:
    print("⚠️  Качество хорошее, но скорость можно улучшить")
elif avg_time < 1.0:
    print("⚠️  Скорость хорошая, но качество нужно улучшить")
else:
    print("❌ Нужны дальнейшие оптимизации")
print()
