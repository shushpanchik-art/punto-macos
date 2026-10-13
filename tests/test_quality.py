#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты качества распознавания punto - насколько точно работает автокоррекция
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from punto import convert, decide


class TestRecognitionQuality(unittest.TestCase):
    """Тесты качества распознавания"""

    def test_common_russian_words(self):
        """Распознавание частых русских слов"""
        test_cases = [
            ("ghbdtn", "привет"),  # привет
            ("gjrf", "пока"),      # пока
            ("cnfkj", "стало"),    # стало (было в твоем тесте!)
            ("ntcnbhjdfnm", "тестировать"),
            ("hf,jnftn", "работает"),
            ("crfpfnm", "сказать"),
            ("gjcvjnhbv", "посмотрим"),
        ]

        for input_word, expected in test_cases:
            with self.subTest(word=input_word):
                result = convert(input_word, "ru")
                self.assertEqual(result, expected,
                               f"'{input_word}' → '{result}', ожидалось '{expected}'")

    def test_common_english_words(self):
        """Распознавание частых английских слов"""
        test_cases = [
            ("руддщ", "hello"),
            ("цщклштп", "working"),
            ("лунищфквы", "keyboards"),
            ("пшерги", "github"),
            ("gыерщт", "python"),
            ("срусл", "check"),
        ]

        for input_word, expected in test_cases:
            with self.subTest(word=input_word):
                result = convert(input_word, "en")
                self.assertEqual(result, expected,
                               f"'{input_word}' → '{result}', ожидалось '{expected}'")

    def test_short_words_en(self):
        """Короткие английские слова (2 буквы)"""
        test_cases = [
            ("фь", "am"),
            ("шы", "is"),
            ("тщ", "no"),
            ("щл", "ok"),
            ("ре", "he"),
            ("ьу", "me"),
        ]

        for input_word, expected in test_cases:
            with self.subTest(word=input_word):
                result = convert(input_word, "en")
                self.assertEqual(result, expected)

    def test_short_words_ru(self):
        """Короткие русские слова (2 буквы)"""
        test_cases = [
            ("lf", "да"),
            ("yt", "не"),
            ("yf", "на"),
            ("pf", "за"),
            ("jy", "он"),
        ]

        for input_word, expected in test_cases:
            with self.subTest(word=input_word):
                result = convert(input_word, "ru")
                self.assertEqual(result, expected)

    def test_false_positives(self):
        """Проверка ложных срабатываний - правильные слова не должны меняться"""
        # TODO: Реализовать тест с decide() для проверки что правильные слова не трогаются
        pass

    def test_accuracy_rate(self):
        """Общая точность распознавания на тестовом наборе"""
        # Набор из 100 самых частых слов
        test_set = [
            # Русские слова (английскими буквами)
            ("ghbdtn", "привет"),
            ("gjrf", "пока"),
            ("crfpfnm", "сказать"),
            ("hf,jnftn", "работает"),
            # Английские слова (русскими буквами)
            ("руддщ", "hello"),
            ("цщклштп", "working"),
            ("пшерги", "github"),
            # ... добавить больше слов
        ]

        correct = 0
        total = len(test_set)

        for input_word, expected in test_set:
            # Определяем целевой язык
            target = "ru" if all(ord('a') <= ord(c.lower()) <= ord('z') for c in input_word if c.isalpha()) else "en"
            result = convert(input_word, target)
            if result == expected:
                correct += 1

        accuracy = (correct / total) * 100
        print(f"\n📊 Точность распознавания: {accuracy:.1f}% ({correct}/{total})")

        # Требуем минимум 90% точности
        self.assertGreaterEqual(accuracy, 90.0,
                               f"Точность {accuracy:.1f}% ниже требуемых 90%")


class TestRealWorldScenarios(unittest.TestCase):
    """Тесты реальных сценариев использования"""

    def test_sentence_conversion(self):
        """Конвертация целого предложения"""
        # Предложение набранное в неправильной раскладке
        wrong = "ghbdtn rfr ltkf"  # "привет как дела"
        words = wrong.split()
        converted = " ".join([convert(w, "ru") for w in words])
        self.assertEqual(converted, "привет как дела")

    def test_mixed_language_sentence(self):
        """Предложение со смешанными языками"""
        # "проверим github работает"
        wrong = "ghjdthbv github hf,jnftn"
        # Каждое слово нужно конвертировать в свою раскладку
        # github - правильное, не трогаем
        # TODO: Реализовать определение правильной раскладки для каждого слова
        pass

    def test_code_snippet(self):
        """Код со смешанным текстом"""
        # Частый случай - комментарии в коде в неправильной раскладке
        code_line = "def test():  # ntcnjdsq rjvvtynfhbq"
        # Должно конвертировать только комментарий
        pass


if __name__ == '__main__':
    unittest.main()
