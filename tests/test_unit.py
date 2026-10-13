#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit-тесты для punto - тестирование базовой логики без UI
"""

import unittest
import sys
import os

# Добавляем родительскую директорию в PATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punto import convert, decide, load_words, load_exceptions


class TestConvert(unittest.TestCase):
    """Тесты конвертации между раскладками"""

    def test_en_to_ru(self):
        """Английский → Русский"""
        self.assertEqual(convert("hello", "ru"), "руддщ")
        self.assertEqual(convert("privet", "ru"), "привет")
        self.assertEqual(convert("github", "ru"), "пшерги")

    def test_ru_to_en(self):
        """Русский → Английский"""
        self.assertEqual(convert("привет", "en"), "ghbdtn")
        self.assertEqual(convert("руддщ", "en"), "hello")
        self.assertEqual(convert("пшерги", "en"), "github")

    def test_mixed_text(self):
        """Смешанный текст (только буквы конвертируются)"""
        self.assertEqual(convert("hello123", "ru"), "руддщ123")
        self.assertEqual(convert("test-case", "ru"), "еуые-сфыу")

    def test_special_chars(self):
        """Спецсимволы не конвертируются"""
        self.assertEqual(convert("test!", "ru"), "еуые!")
        self.assertEqual(convert("привет?", "en"), "ghbdtn?")

    def test_case_preservation(self):
        """Регистр сохраняется"""
        self.assertEqual(convert("Hello", "ru"), "Руддщ")
        self.assertEqual(convert("HELLO", "ru"), "РУДДЩ")
        self.assertEqual(convert("Привет", "en"), "Ghbdtn")


class TestDecide(unittest.TestCase):
    """Тесты определения нужной раскладки"""

    def test_correct_layout_no_fix(self):
        """Слово в правильной раскладке - не трогаем"""
        # Эти тесты требуют загруженных словарей
        # Мы их пропускаем если словари не загружены
        pass

    def test_short_words(self):
        """Короткие слова (2 буквы)"""
        # am, da, no и т.д. должны корректно обрабатываться
        pass

    def test_exceptions(self):
        """Слова из exceptions.txt не трогаем"""
        pass


class TestLoadWords(unittest.TestCase):
    """Тесты загрузки словарей"""

    def test_load_existing_file(self):
        """Загрузка существующего файла"""
        # Проверяем что словарь загружается
        words = load_words("words_en.txt", "test fallback")
        self.assertIsInstance(words, set)
        self.assertGreater(len(words), 0)

    def test_load_nonexistent_file(self):
        """Загрузка несуществующего файла - fallback"""
        words = load_words("nonexistent.txt", "hello world test")
        self.assertEqual(words, {"hello", "world", "test"})

    def test_load_exceptions(self):
        """Загрузка исключений"""
        exceptions = load_exceptions("exceptions.txt")
        self.assertIsInstance(exceptions, set)


class TestShortWords(unittest.TestCase):
    """Критический тест - SHORT_EN и SHORT_RU должны быть определены"""

    def test_short_en_defined(self):
        """SHORT_EN определен"""
        from punto import SHORT_EN
        self.assertIsInstance(SHORT_EN, set)
        self.assertIn("am", SHORT_EN)
        self.assertIn("is", SHORT_EN)
        self.assertIn("no", SHORT_EN)

    def test_short_ru_defined(self):
        """SHORT_RU определен"""
        from punto import SHORT_RU
        self.assertIsInstance(SHORT_RU, set)
        self.assertIn("да", SHORT_RU)
        self.assertIn("не", SHORT_RU)
        self.assertIn("на", SHORT_RU)

    def test_short_word_conversion(self):
        """Конвертация коротких слов"""
        self.assertEqual(convert("am", "ru"), "ам")
        self.assertEqual(convert("да", "en"), "lf")
        self.assertEqual(convert("no", "ru"), "тщ")


if __name__ == '__main__':
    unittest.main()
