#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для punto.py
"""

import unittest
import sys
import os

# Добавляем путь к punto.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем функции из punto.py
from punto import convert, TO_EN, TO_RU, EN_LOWER, RU_LOWER


class TestConversion(unittest.TestCase):
    """Тесты конвертации текста между раскладками"""

    def test_en_to_ru_lower(self):
        """Конвертация английских букв в русские (нижний регистр)"""
        # Преобразование по позициям клавиш
        self.assertEqual(convert("ghbdtn", "ru"), "привет")
        self.assertEqual(convert("hello", "ru"), "руддщ")
        self.assertEqual(convert("test", "ru"), "еуые")

    def test_ru_to_en_lower(self):
        """Конвертация русских букв в английские (нижний регистр)"""
        self.assertEqual(convert("привет", "en"), "ghbdtn")
        self.assertEqual(convert("руддщ", "en"), "hello")
        self.assertEqual(convert("еуые", "en"), "test")

    def test_en_to_ru_upper(self):
        """Конвертация английских букв в русские (верхний регистр)"""
        self.assertEqual(convert("GHBDTN", "ru"), "ПРИВЕТ")
        self.assertEqual(convert("HELLO", "ru"), "РУДДЩ")

    def test_ru_to_en_upper(self):
        """Конвертация русских букв в английские (верхний регистр)"""
        self.assertEqual(convert("ПРИВЕТ", "en"), "GHBDTN")
        self.assertEqual(convert("РУДДЩ", "en"), "HELLO")

    def test_mixed_case(self):
        """Конвертация смешанного регистра"""
        self.assertEqual(convert("Ghbdtn", "ru"), "Привет")
        self.assertEqual(convert("Привет", "en"), "Ghbdtn")

    def test_symbols_unchanged(self):
        """Символы, не входящие в раскладку, остаются без изменений"""
        self.assertEqual(convert("hello123", "ru"), "руддщ123")
        self.assertEqual(convert("привет!", "en"), "ghbdtn!")
        self.assertEqual(convert("test@example.com", "ru"), "еуые@учфьздуюсщь")

    def test_empty_string(self):
        """Пустая строка остаётся пустой"""
        self.assertEqual(convert("", "ru"), "")
        self.assertEqual(convert("", "en"), "")

    def test_numbers_unchanged(self):
        """Цифры не меняются"""
        self.assertEqual(convert("12345", "ru"), "12345")
        self.assertEqual(convert("12345", "en"), "12345")


class TestMappingTables(unittest.TestCase):
    """Тесты таблиц соответствия клавиш"""

    def test_en_ru_mapping_length(self):
        """Длина таблиц EN и RU должна совпадать"""
        self.assertEqual(len(EN_LOWER), len(RU_LOWER))

    def test_bidirectional_mapping(self):
        """Проверка обратимости конвертации"""
        test_text = "qwertyuiop"
        ru_text = convert(test_text, "ru")
        back_to_en = convert(ru_text, "en")
        self.assertEqual(test_text, back_to_en)

    def test_to_ru_keys(self):
        """Проверка ключей в словаре TO_RU"""
        # Проверяем, что все английские буквы есть в словаре
        for char in EN_LOWER:
            self.assertIn(char, TO_RU)

    def test_to_en_keys(self):
        """Проверка ключей в словаре TO_EN"""
        # Проверяем, что все русские буквы есть в словаре
        for char in RU_LOWER:
            self.assertIn(char, TO_EN)


class TestSpecialCases(unittest.TestCase):
    """Тесты специальных случаев"""

    def test_yo_letter(self):
        """Проверка буквы ё"""
        # Буква ё должна конвертироваться в `
        self.assertEqual(convert("`", "ru"), "ё")
        self.assertEqual(convert("ё", "en"), "`")

    def test_brackets_and_quotes(self):
        """Проверка скобок и кавычек"""
        self.assertEqual(convert("[]", "ru"), "хъ")
        self.assertEqual(convert("хъ", "en"), "[]")
        self.assertEqual(convert("'", "ru"), "э")
        self.assertEqual(convert("э", "en"), "'")


if __name__ == "__main__":
    # Запускаем тесты с подробным выводом
    unittest.main(verbosity=2)
