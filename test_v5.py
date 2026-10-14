#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест punto_v5 на реальных данных пользователя
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

# РЕАЛЬНЫЙ ТЕСТ из сообщения пользователя
REAL_TEST = [
    ("рщw", "ru", "how"),       # Смешанная раскладка!
    ("ns", "ru", "ты"),         # Короткое
    ("ьу", "en", "by"),         # Короткое
    ("yt", "ru", "не"),         # Короткое
    ("шts", "ru", "its"),       # Смешанная раскладка!
    ("d", "ru", "в"),           # Однобуквенное
    ("иге", "en", "yet"),       # Короткое (3 буквы)
]

# Стандартный тест из начала сессии
STANDARD_TEST = [
    ("еуые", "en", "test"),
    ("цщклы", "en", "work"),
    ("crfxfpfnm", "ru", "сказать"),
    ("ерfе", "en", "that"),
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
print("ТЕСТ PUNTO V5 - СМЕШАННЫЕ РАСКЛАДКИ + КОРОТКИЕ СЛОВА")
print("="*70 + "\n")

print("📊 Загрузка punto_v5.py...")
punto = load_module("punto_v5.py")

# Тест 1: Реальные данные пользователя
print("\n" + "─"*70)
print("ТЕСТ 1: РЕАЛЬНЫЕ ПРОБЛЕМНЫЕ СЛОВА")
print("─"*70 + "\n")

passed_real = 0
for wrong, target_lang, correct in REAL_TEST:
    result = punto.decide(wrong)
    converted = punto.convert(wrong, target_lang) if target_lang else None

    if result == target_lang:
        print(f"✅ '{wrong}' → {result} → '{converted}' (ожидалось '{correct}')")
        passed_real += 1
    else:
        print(f"❌ '{wrong}' → {result} (ожидалось {target_lang} → '{correct}')")

quality_real = passed_real / len(REAL_TEST) * 100
print(f"\nРеальный тест: {passed_real}/{len(REAL_TEST)} = {quality_real:.1f}%")

# Тест 2: Стандартный тест
print("\n" + "─"*70)
print("ТЕСТ 2: СТАНДАРТНЫЕ СЛОВА")
print("─"*70 + "\n")

passed_std = 0
for wrong, target_lang, correct in STANDARD_TEST:
    result = punto.decide(wrong)
    if result == target_lang:
        print(f"✅ '{wrong}' → {result}")
        passed_std += 1
    else:
        print(f"❌ '{wrong}' → {result} (ожидалось {target_lang})")

quality_std = passed_std / len(STANDARD_TEST) * 100
print(f"\nСтандартный тест: {passed_std}/{len(STANDARD_TEST)} = {quality_std:.1f}%")

# Тест производительности
print("\n" + "─"*70)
print("ТЕСТ ПРОИЗВОДИТЕЛЬНОСТИ")
print("─"*70 + "\n")

all_words = [w[0] for w in REAL_TEST + STANDARD_TEST]
times = []

for word in all_words:
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
print("                 Реальный   Стандарт   Скорость   Особенности")
print("─"*70)
print(f"punto.py         ???        58.3%      0.002ms    Словарь")
print(f"punto_v3.py      42.9%      100.0%     0.010ms    Fuzzy")
print(f"punto_v4.py      ???        83.3%      0.027ms    N-граммы")
print(f"punto_v5.py      {quality_real:5.1f}%     {quality_std:5.1f}%     {avg_time:.3f}ms    Гибрид")
print()

# Оценка
improvement_real = quality_real - 42.9
improvement_std = quality_std - 100.0

print("📈 УЛУЧШЕНИЕ:")
if improvement_real > 0:
    print(f"   ✅ Реальный тест: +{improvement_real:.1f}% (было 42.9%)")
else:
    print(f"   ⚠️  Реальный тест: {improvement_real:.1f}% (было 42.9%)")

if improvement_std >= 0:
    print(f"   ✅ Стандартный тест: {improvement_std:+.1f}% (было 100.0%)")
else:
    print(f"   ⚠️  Стандартный тест: {improvement_std:.1f}% (было 100.0%)")

print()

if quality_real >= 80 and quality_std >= 95:
    print("🎉 ОТЛИЧНО! Версия v5 решила проблемы!")
elif quality_real >= 70:
    print("✅ ХОРОШО! Значительное улучшение на реальных данных")
else:
    print("⚠️  Нужны дополнительные доработки")

print()
