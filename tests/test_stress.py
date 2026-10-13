#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Стресс-тесты для punto - проверка стабильности под нагрузкой
"""

import unittest
import sys
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punto import convert


class TestStress(unittest.TestCase):
    """Стресс-тесты punto"""

    def test_1000_consecutive_conversions(self):
        """1000 последовательных конвертаций без падения"""
        print("\n🔥 Стресс-тест: 1000 конвертаций...")

        words = ["hello", "world", "test", "github", "python", "работает", "проверка"]
        start = time.time()

        for i in range(1000):
            for word in words:
                convert(word, "ru")
                convert(word, "en")

        elapsed = time.time() - start
        print(f"✅ Завершено за {elapsed:.2f}с ({1000*len(words)*2/elapsed:.0f} конв/сек)")

        # Должно завершиться за разумное время (< 10 сек)
        self.assertLess(elapsed, 10.0)

    def test_rapid_fire_conversions(self):
        """Очень быстрые конвертации (имитация быстрого ввода)"""
        print("\n⚡ Стресс-тест: быстрый ввод...")

        for i in range(500):
            convert("test", "ru")
            time.sleep(0.001)  # 1ms между конвертациями (очень быстрый ввод)

        print("✅ Быстрый ввод обработан без ошибок")

    def test_parallel_conversions(self):
        """Параллельные конвертации (multi-threading)"""
        print("\n🔀 Стресс-тест: параллельная обработка...")

        def worker(thread_id):
            for i in range(100):
                convert(f"test{thread_id}_{i}", "ru")
                convert(f"тест{thread_id}_{i}", "en")

        start = time.time()
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(20)]
            for future in futures:
                future.result()

        elapsed = time.time() - start
        total_ops = 20 * 100 * 2
        print(f"✅ {total_ops} операций за {elapsed:.2f}с ({total_ops/elapsed:.0f} оп/сек)")

    def test_long_text_stress(self):
        """Конвертация очень длинного текста"""
        print("\n📝 Стресс-тест: длинный текст...")

        # 10000 слов
        long_text = " ".join(["hello"] * 10000)
        start = time.time()
        result = convert(long_text, "ru")
        elapsed = time.time() - start

        print(f"✅ 10000 слов обработано за {elapsed:.2f}с")
        self.assertEqual(len(result), len(long_text))
        self.assertLess(elapsed, 5.0)  # Должно быть быстро

    def test_memory_stability(self):
        """Проверка стабильности памяти при длительной работе"""
        print("\n💾 Стресс-тест: стабильность памяти...")

        import tracemalloc
        tracemalloc.start()

        start_mem = tracemalloc.get_traced_memory()[0]

        # Имитация долгой работы
        for batch in range(10):
            for i in range(100):
                convert(f"test{batch}_{i}", "ru")
                convert(f"тест{batch}_{i}", "en")

        end_mem = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()

        mem_increase_mb = (end_mem - start_mem) / 1024 / 1024
        print(f"💾 Прирост памяти: {mem_increase_mb:.2f}MB")

        # Прирост памяти должен быть разумным (< 5MB)
        self.assertLess(mem_increase_mb, 5.0,
                       f"Возможна утечка памяти: {mem_increase_mb:.2f}MB")

    def test_exception_recovery(self):
        """Восстановление после исключений"""
        print("\n🛡️ Стресс-тест: обработка ошибок...")

        # Нормальные операции перемежаются с некорректными
        for i in range(100):
            try:
                convert("test", "ru")
                convert(None, "en")  # Должно вызвать ошибку
            except:
                pass
            convert("hello", "ru")  # Должно работать после ошибки

        print("✅ Восстановление после ошибок работает")


class TestPerformance(unittest.TestCase):
    """Тесты производительности"""

    def test_conversion_speed(self):
        """Скорость конвертации"""
        print("\n⏱️ Тест производительности...")

        iterations = 10000
        start = time.time()

        for i in range(iterations):
            convert("hello", "ru")

        elapsed = time.time() - start
        ops_per_sec = iterations / elapsed

        print(f"⚡ Производительность: {ops_per_sec:.0f} конв/сек")

        # Должно быть минимум 1000 конвертаций в секунду
        self.assertGreater(ops_per_sec, 1000,
                          f"Слишком медленно: {ops_per_sec:.0f} конв/сек")

    def test_short_vs_long_words(self):
        """Сравнение скорости для коротких и длинных слов"""
        print("\n📊 Сравнение производительности...")

        short_word = "hi"
        long_word = "internationalization"
        iterations = 5000

        # Короткие слова
        start = time.time()
        for _ in range(iterations):
            convert(short_word, "ru")
        short_time = time.time() - start

        # Длинные слова
        start = time.time()
        for _ in range(iterations):
            convert(long_word, "ru")
        long_time = time.time() - start

        print(f"  Короткие слова: {iterations/short_time:.0f} конв/сек")
        print(f"  Длинные слова: {iterations/long_time:.0f} конв/сек")
        print(f"  Разница: {short_time/long_time:.2f}x")


if __name__ == '__main__':
    unittest.main(verbosity=2)
