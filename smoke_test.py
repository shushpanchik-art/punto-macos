#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke test для punto - автоматическое тестирование без GUI
"""

import sys
import os
import time
import importlib.util

# Добавляем путь к punto
PUNTO_DIR = os.path.expanduser("~/punto")
sys.path.insert(0, PUNTO_DIR)

# Импортируем функции из punto
spec = importlib.util.spec_from_file_location("punto", os.path.join(PUNTO_DIR, "punto.py"))
punto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(punto)

# Тестовые случаи
TEST_CASES = [
    # (input_word, expected_lang, expected_output, description)
    ("ghbdtn", "ru", "привет", "Английская -> Русская: привет"),
    ("руддщ", "en", "hello", "Русская -> Английская: hello"),
    ("rfr", "ru", "как", "Короткое слово: как"),
    ("рщц", "en", "how", "Короткое слово: how"),
    ("ntktajy", "ru", "телефон", "Среднее слово: телефон"),
    ("hf,jnftn", "ru", "работает", "Длинное слово: работает"),
    ("rfxtcndj", "ru", "качество", "Качество"),
    ("wtkjv", "ru", "целом", "Целом"),
    ("vyjuj", "ru", "много", "Много"),
    ("jxtym", "ru", "очень", "Очень"),
    ("ytcvjnhz", "ru", "несмотря", "Несмотря"),
    ("gjghj,etv", "ru", "попробуем", "Попробуем"),
    ("testing", "en", "testing", "Правильное английское слово (не менять)"),
    ("привет", "ru", "привет", "Правильное русское слово (не менять)"),
]

def test_decide_function():
    """Тестирует функцию decide() из punto"""
    print("=" * 60)
    print("SMOKE TEST: Тестирование функции decide()")
    print("=" * 60)
    print()

    passed = 0
    failed = 0
    errors = []

    for word, expected_lang, expected_output, description in TEST_CASES:
        try:
            result = punto.decide(word)

            # Если слово правильное, decide должна вернуть None
            if word == expected_output:
                if result is None:
                    print(f"✅ PASS: {description}")
                    print(f"   Вход: '{word}' -> Результат: None (правильно, не менять)")
                    passed += 1
                else:
                    print(f"❌ FAIL: {description}")
                    print(f"   Вход: '{word}' -> Ожидалось: None, Получено: {result}")
                    failed += 1
                    errors.append((word, None, result, description))
            else:
                # Проверяем конвертацию
                converted = punto.convert(word, expected_lang) if result else None

                if result == expected_lang and converted == expected_output:
                    print(f"✅ PASS: {description}")
                    print(f"   Вход: '{word}' -> Язык: {result} -> Вывод: '{converted}'")
                    passed += 1
                elif result is None:
                    print(f"❌ FAIL: {description}")
                    print(f"   Вход: '{word}' -> decide() вернула None (не распознано)")
                    print(f"   Ожидалось: язык={expected_lang}, вывод='{expected_output}'")
                    failed += 1
                    errors.append((word, expected_lang, None, description))
                else:
                    print(f"❌ FAIL: {description}")
                    print(f"   Вход: '{word}' -> Язык: {result} -> Вывод: '{converted}'")
                    print(f"   Ожидалось: язык={expected_lang}, вывод='{expected_output}'")
                    failed += 1
                    errors.append((word, expected_lang, result, description))
        except Exception as e:
            print(f"❌ ERROR: {description}")
            print(f"   Вход: '{word}' -> Исключение: {e}")
            failed += 1
            errors.append((word, expected_lang, f"Exception: {e}", description))

        print()

    # Итоги
    print("=" * 60)
    print("РЕЗУЛЬТАТЫ ТЕСТА")
    print("=" * 60)
    print(f"Всего тестов: {passed + failed}")
    print(f"✅ Пройдено: {passed}")
    print(f"❌ Провалено: {failed}")
    print(f"Процент успеха: {(passed / (passed + failed) * 100):.1f}%")
    print()

    if errors:
        print("ПРОВАЛИВШИЕСЯ ТЕСТЫ:")
        print("-" * 60)
        for word, expected, got, desc in errors:
            print(f"• {desc}")
            print(f"  Слово: '{word}'")
            print(f"  Ожидалось: {expected}")
            print(f"  Получено: {got}")
            print()

    return passed, failed


def test_dictionary_coverage():
    """Проверяет покрытие словарей"""
    print("=" * 60)
    print("SMOKE TEST: Проверка словарей")
    print("=" * 60)
    print()

    print(f"Английских слов: {len(punto.EN_WORDS):,}")
    print(f"Русских слов: {len(punto.RU_WORDS):,}")
    print(f"Исключений: {len(punto.EXCEPTIONS):,}")
    print()

    # Проверяем популярные слова
    common_en = ["the", "and", "you", "that", "have", "for", "not", "with", "this"]
    common_ru = ["и", "в", "не", "на", "что", "он", "я", "с", "как"]

    en_missing = [w for w in common_en if w not in punto.EN_WORDS]
    ru_missing = [w for w in common_ru if w not in punto.RU_WORDS]

    if not en_missing:
        print("✅ Все популярные английские слова в словаре")
    else:
        print(f"❌ Отсутствуют английские слова: {en_missing}")

    if not ru_missing:
        print("✅ Все популярные русские слова в словаре")
    else:
        print(f"❌ Отсутствуют русские слова: {ru_missing}")

    print()


def test_convert_function():
    """Тестирует функцию конвертации"""
    print("=" * 60)
    print("SMOKE TEST: Тестирование функции convert()")
    print("=" * 60)
    print()

    test_pairs = [
        ("ghbdtn", "ru", "привет"),
        ("руддщ", "en", "hello"),
        ("rfr", "ru", "как"),
        ("рщц", "en", "how"),
    ]

    passed = 0
    failed = 0

    for input_text, to_lang, expected in test_pairs:
        result = punto.convert(input_text, to_lang)
        if result == expected:
            print(f"✅ PASS: '{input_text}' -> {to_lang} -> '{result}'")
            passed += 1
        else:
            print(f"❌ FAIL: '{input_text}' -> {to_lang}")
            print(f"   Ожидалось: '{expected}', Получено: '{result}'")
            failed += 1
        print()

    print(f"Конвертация: {passed}/{passed+failed} тестов пройдено")
    print()

    return passed, failed


def main():
    """Запуск всех тестов"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "PUNTO SMOKE TEST" + " " * 27 + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    start_time = time.time()

    # Тест 1: Словари
    test_dictionary_coverage()

    # Тест 2: Конвертация
    convert_passed, convert_failed = test_convert_function()

    # Тест 3: Основная логика
    decide_passed, decide_failed = test_decide_function()

    # Финальный отчёт
    elapsed = time.time() - start_time
    total_passed = convert_passed + decide_passed
    total_failed = convert_failed + decide_failed

    print("=" * 60)
    print("ФИНАЛЬНЫЙ ОТЧЁТ")
    print("=" * 60)
    print(f"Всего тестов выполнено: {total_passed + total_failed}")
    print(f"✅ Пройдено: {total_passed}")
    print(f"❌ Провалено: {total_failed}")
    print(f"⏱️  Время выполнения: {elapsed:.2f} секунд")
    print()

    if total_failed == 0:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print("⚠️  ЕСТЬ ПРОВАЛЕННЫЕ ТЕСТЫ")
        print()
        print("РЕКОМЕНДАЦИИ:")
        if decide_failed > 0:
            print("• Проверьте логику функции decide()")
            print("• Убедитесь, что словари загружены правильно")
            print("• Проверьте определение has_cyrillic и has_latin")
        return 1


if __name__ == "__main__":
    sys.exit(main())
