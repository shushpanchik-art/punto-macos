#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест punto_v4 с частотным анализом
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

# Тестовые слова
TEST_CASES = [
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
print("ТЕСТ PUNTO V4 - ЧАСТОТНЫЙ АНАЛИЗ N-ГРАММ")
print("="*70 + "\n")

print("📊 Загрузка punto_v4.py...")
punto = load_module("punto_v4.py")

# Тест качества
print("\n" + "─"*70)
print("ТЕСТ КАЧЕСТВА")
print("─"*70 + "\n")

passed = 0
for wrong, lang, correct in TEST_CASES:
    result = punto.decide(wrong)
    if result == lang:
        print(f"✅ '{wrong}' → {lang}")
        passed += 1
    else:
        print(f"❌ '{wrong}' → {result} (ожидалось {lang})")

quality = passed / len(TEST_CASES) * 100
print(f"\nКачество: {passed}/{len(TEST_CASES)} = {quality:.1f}%")

# Тест производительности
print("\n" + "─"*70)
print("ТЕСТ ПРОИЗВОДИТЕЛЬНОСТИ")
print("─"*70 + "\n")

words_for_bench = [w[0] for w in TEST_CASES]
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

# Дополнительные тесты - слова без словаря
print("\n" + "─"*70)
print("ТЕСТ БЕЗ СЛОВАРЯ (только статистика)")
print("─"*70 + "\n")

extra_tests = [
    ("ghbdtnbr", "ru", "приветик"),  # Неологизм
    ("ghjdth", "ru", "провер"),       # Неполное слово
    ("rfxtcndtyyjq", "ru", "качественной"),  # Длинное слово
]

print("Эти слова ОТСУТСТВУЮТ в словаре, только n-граммы:")
extra_passed = 0
for wrong, lang, expected in extra_tests:
    result = punto.decide(wrong)
    if result == lang:
        print(f"✅ '{wrong}' → {lang} → '{punto.convert(wrong, lang)}'")
        extra_passed += 1
    else:
        print(f"❌ '{wrong}' → {result} (ожидалось {lang})")

print(f"\nРезультат: {extra_passed}/{len(extra_tests)}")

# Итоговое сравнение
print("\n" + "="*70)
print("СРАВНЕНИЕ ВЕРСИЙ")
print("="*70)
print()
print("                    Качество    Скорость    Подход")
print("─"*70)
print(f"punto.py            58.3%       0.002 ms    Словарь")
print(f"punto_v3.py         100.0%      0.010 ms    Словарь + Fuzzy")
print(f"punto_v4.py         {quality:5.1f}%      {avg_time:5.3f} ms    N-граммы")
print()

if quality >= 90:
    print("✅ Отличное качество!")
if avg_time < 0.1:
    print("✅ Отличная скорость!")

print("\n💡 ПРЕИМУЩЕСТВА V4:")
print("   • Не требует полного словаря")
print("   • Распознаёт неологизмы и опечатки")
print("   • Работает на основе статистики языка")
print()
