#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Интеграционные тесты для punto - проверка реальной работы
"""

import unittest
import sys
import os
import time
import threading
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPuntoIntegration(unittest.TestCase):
    """Интеграционные тесты punto"""

    def test_punto_startup(self):
        """Punto запускается без ошибок"""
        # Импортируем основные компоненты
        try:
            import punto
            self.assertTrue(hasattr(punto, 'convert'))
            self.assertTrue(hasattr(punto, 'decide'))
            self.assertTrue(hasattr(punto, 'SHORT_EN'))
            self.assertTrue(hasattr(punto, 'SHORT_RU'))
        except ImportError as e:
            self.fail(f"Failed to import punto: {e}")

    def test_dictionaries_loaded(self):
        """Словари загружены корректно"""
        import punto
        self.assertIsInstance(punto.EN_WORDS, set)
        self.assertIsInstance(punto.RU_WORDS, set)
        self.assertGreater(len(punto.EN_WORDS), 1000)
        self.assertGreater(len(punto.RU_WORDS), 1000)

    def test_layout_detection(self):
        """Определение текущей раскладки"""
        from punto import current_layout
        layout = current_layout()
        self.assertIn(layout, ["en", "ru"])

    def test_no_memory_leak_on_convert(self):
        """Конвертация не создает утечек памяти"""
        from punto import convert
        import tracemalloc

        tracemalloc.start()
        start = tracemalloc.get_traced_memory()[0]

        # 10000 конвертаций
        for i in range(10000):
            convert(f"test{i}", "ru")
            convert(f"тест{i}", "en")

        end = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()

        # Прирост памяти должен быть минимальным (< 1MB)
        memory_increase = (end - start) / 1024 / 1024
        self.assertLess(memory_increase, 1.0,
                       f"Memory leak detected: {memory_increase:.2f}MB increase")


class TestPuntoStability(unittest.TestCase):
    """Тесты стабильности punto"""

    def test_rapid_conversions(self):
        """Быстрые последовательные конвертации"""
        from punto import convert

        words = ["hello", "world", "test", "github", "python"]
        for _ in range(1000):
            for word in words:
                convert(word, "ru")
                convert(word, "en")

    def test_concurrent_conversions(self):
        """Параллельные конвертации (thread-safety)"""
        from punto import convert

        def worker():
            for i in range(100):
                convert(f"test{i}", "ru")
                convert(f"тест{i}", "en")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_long_text_conversion(self):
        """Конвертация длинного текста"""
        from punto import convert

        long_text = "hello " * 1000
        result = convert(long_text, "ru")
        self.assertEqual(len(result), len(long_text))


class TestPuntoEdgeCases(unittest.TestCase):
    """Граничные случаи"""

    def test_empty_string(self):
        """Пустая строка"""
        from punto import convert
        self.assertEqual(convert("", "ru"), "")
        self.assertEqual(convert("", "en"), "")

    def test_single_char(self):
        """Один символ"""
        from punto import convert
        self.assertEqual(convert("a", "ru"), "ф")
        self.assertEqual(convert("ф", "en"), "f")

    def test_numbers_only(self):
        """Только цифры"""
        from punto import convert
        self.assertEqual(convert("12345", "ru"), "12345")
        self.assertEqual(convert("12345", "en"), "12345")

    def test_special_chars_only(self):
        """Только спецсимволы"""
        from punto import convert
        self.assertEqual(convert("!@#$%", "ru"), "!@#$%")
        self.assertEqual(convert("!@#$%", "en"), "!@#$%")

    def test_unicode_emoji(self):
        """Unicode и эмодзи"""
        from punto import convert
        text = "hello 👋 test 🎉"
        result = convert(text, "ru")
        # Эмодзи должны остаться на месте
        self.assertIn("👋", result)
        self.assertIn("🎉", result)


if __name__ == '__main__':
    unittest.main()
