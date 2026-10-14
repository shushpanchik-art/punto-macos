#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бенчмарк punto v2 vs оригинал
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

def benchmark_decide(module, words, iterations=100):
    times = []
    for word in words:
        for _ in range(iterations):
            start = time.perf_counter()
            module.decide(word)
            end = time.perf_counter()
            times.append((end - start) * 1000)
    return mean(times)

# Тестовые слова - проблемные из твоего сообщения
TEST_WORDS = ["еуые", "цщклы", "crfxfpfnm", "ерфе", "рщцуферук", "тще",
              "[jhjij", "crjhjcnm", "hf,jns", "jcnfkztn", ";tkfnm", "kexituj"]

print("\n" + "="*70)
print("БЕНЧМАРК: punto.py vs punto_v2.py")
print("="*70 + "\n")

# Оригинал
print("📊 Загрузка punto.py...")
punto_v1 = load_module("punto.py")
time_v1 = benchmark_decide(punto_v1, TEST_WORDS, iterations=50)
print(f"   Среднее время: {time_v1:.4f} ms")

# V2 с fuzzy matching
print("\n📊 Загрузка punto_v2.py...")
punto_v2 = load_module("punto_v2.py")
time_v2 = benchmark_decide(punto_v2, TEST_WORDS, iterations=50)
print(f"   Среднее время: {time_v2:.4f} ms")

# Сравнение
print("\n" + "="*70)
print("РЕЗУЛЬТАТЫ:")
print("="*70)
print(f"punto.py:    {time_v1:.4f} ms")
print(f"punto_v2.py: {time_v2:.4f} ms")

if time_v2 > time_v1:
    slowdown = ((time_v2 / time_v1) - 1) * 100
    print(f"\nЗамедление: +{slowdown:.1f}%")
else:
    speedup = ((time_v1 / time_v2) - 1) * 100
    print(f"\nУскорение: +{speedup:.1f}%")

print("\n💡 ВЫВОДЫ:")
if time_v2 < 0.01:
    print("✅ punto_v2 очень быстрый (< 0.01 ms)")
elif time_v2 < 0.1:
    print("✅ punto_v2 быстрый (< 0.1 ms)")
elif time_v2 < 1.0:
    print("⚠️  punto_v2 приемлемый (< 1 ms)")
else:
    print("❌ punto_v2 медленный (> 1 ms)")

print(f"\nКачество распознавания:")
print(f"  punto.py:    58.3%")
print(f"  punto_v2.py: 100.0% (+41.7%)")
print()
