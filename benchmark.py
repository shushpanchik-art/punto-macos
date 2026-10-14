#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark для punto - тест производительности
"""

import sys
import os
import time
import importlib.util
from statistics import mean, median, stdev

PUNTO_DIR = os.path.expanduser("~/punto")
sys.path.insert(0, PUNTO_DIR)

# Тестовые слова разной длины
TEST_WORDS = {
    "короткие (2-3)": ["rfr", "рщц", "kb", "ты", "ghb", "был"],
    "средние (5-7)": ["ghbdtn", "руддщ", "ntktajy", "качество", "testing", "работа"],
    "длинные (8-12)": ["hf,jnftn", "качественно", "gjghj,etv", "несмотря", "telephone", "разработка"],
    "очень длинные (13+)": ["ghjntcnbhetv", "профессионально", "характеристика", "documentation"],
}

def load_punto_module(filepath):
    """Загружает punto модуль из файла"""
    spec = importlib.util.spec_from_file_location("punto", filepath)
    punto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(punto)
    return punto

def benchmark_decide(punto_module, words, iterations=100):
    """Бенчмарк функции decide()"""
    times = []

    for word in words:
        word_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            punto_module.decide(word)
            end = time.perf_counter()
            word_times.append((end - start) * 1000)  # в миллисекундах
        times.extend(word_times)

    return {
        "mean": mean(times),
        "median": median(times),
        "min": min(times),
        "max": max(times),
        "stdev": stdev(times) if len(times) > 1 else 0,
    }

def benchmark_convert(punto_module, words, iterations=100):
    """Бенчмарк функции convert()"""
    times = []

    for word in words:
        word_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            punto_module.convert(word, "ru")
            punto_module.convert(word, "en")
            end = time.perf_counter()
            word_times.append((end - start) * 1000)  # в миллисекундах
        times.extend(word_times)

    return {
        "mean": mean(times),
        "median": median(times),
        "min": min(times),
        "max": max(times),
        "stdev": stdev(times) if len(times) > 1 else 0,
    }

def print_results(name, results):
    """Красиво выводит результаты"""
    print(f"  ⏱️  {name}:")
    print(f"     Среднее:  {results['mean']:.4f} ms")
    print(f"     Медиана:  {results['median']:.4f} ms")
    print(f"     Мин/Макс: {results['min']:.4f} / {results['max']:.4f} ms")
    print(f"     Ст.откл:  {results['stdev']:.4f} ms")

def main():
    versions = [
        ("punto.py", "Базовая версия"),
        ("punto_fast.py", "Быстрая версия"),
        ("punto_ultimate.py", "Ultimate версия"),
        ("punto_hybrid.py", "Гибридная версия"),
    ]

    print("\n" + "="*70)
    print(" "*20 + "PUNTO BENCHMARK")
    print("="*70 + "\n")

    for filename, description in versions:
        filepath = os.path.join(PUNTO_DIR, filename)
        if not os.path.exists(filepath):
            print(f"⚠️  {filename} не найден, пропускаем\n")
            continue

        print(f"📊 {description} ({filename})")
        print("-"*70)

        try:
            punto = load_punto_module(filepath)

            # Тест по категориям слов
            for category, words in TEST_WORDS.items():
                print(f"\n  📝 {category}:")

                # decide()
                decide_results = benchmark_decide(punto, words, iterations=50)
                print(f"    decide():  {decide_results['mean']:.4f} ms (медиана: {decide_results['median']:.4f} ms)")

                # convert()
                convert_results = benchmark_convert(punto, words, iterations=50)
                print(f"    convert(): {convert_results['mean']:.4f} ms (медиана: {convert_results['median']:.4f} ms)")

            print("\n")

        except Exception as e:
            print(f"  ❌ Ошибка: {e}\n")

    print("="*70)
    print("\n💡 Рекомендации:")
    print("  • Для повседневной работы: punto.py или punto_fast.py")
    print("  • Для максимальной скорости: punto_ultimate.py")
    print("  • Для баланса: punto_hybrid.py")
    print()

if __name__ == "__main__":
    main()
