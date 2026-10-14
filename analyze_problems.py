#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Детальный анализ почему punto плохо распознаёт слова
"""

import sys
import os
import importlib.util

PUNTO_DIR = os.path.expanduser("~/punto")
sys.path.insert(0, PUNTO_DIR)

def load_punto():
    spec = importlib.util.spec_from_file_location("punto", os.path.join(PUNTO_DIR, "punto.py"))
    punto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(punto)
    return punto

def analyze_word(punto, wrong_word, expected_lang, correct_word):
    """Детальный анализ почему слово не распознаётся"""
    print(f"\n{'='*70}")
    print(f"Анализ слова: '{wrong_word}' → должно быть '{correct_word}' ({expected_lang})")
    print('='*70)

    w = wrong_word.lower().replace("ё", "е")

    # Проверяем, что вернёт decide()
    result = punto.decide(wrong_word)
    print(f"1. decide() вернула: {result}")

    # Определяем язык исходного слова
    has_cyrillic = any('Ѐ' <= c <= 'ӿ' for c in w)
    has_latin = any('a' <= c.lower() <= 'z' for c in w)

    print(f"2. Символы в слове:")
    print(f"   - Кириллица: {has_cyrillic}")
    print(f"   - Латиница: {has_latin}")

    # Проверяем исходное слово в словарях
    in_en = w in punto.EN_WORDS
    in_ru = w in punto.RU_WORDS
    print(f"3. Исходное слово '{w}' в словарях:")
    print(f"   - EN_WORDS: {in_en}")
    print(f"   - RU_WORDS: {in_ru}")

    # Конвертируем в оба языка
    ru_variant = punto.convert(w, "ru").replace("ё", "е")
    en_variant = punto.convert(w, "en")

    print(f"4. Конвертация:")
    print(f"   - В русский: '{ru_variant}'")
    print(f"   - В английский: '{en_variant}'")

    # Проверяем конвертированные варианты в словарях
    ru_in_dict = ru_variant in punto.RU_WORDS
    en_in_dict = en_variant in punto.EN_WORDS

    print(f"5. Конвертированные слова в словарях:")
    print(f"   - '{ru_variant}' в RU_WORDS: {ru_in_dict}")
    print(f"   - '{en_variant}' в EN_WORDS: {en_in_dict}")

    # Проверяем правильное слово
    correct_lower = correct_word.lower().replace("ё", "е")
    correct_in_ru = correct_lower in punto.RU_WORDS
    correct_in_en = correct_lower in punto.EN_WORDS

    print(f"6. Правильное слово '{correct_word}' в словарях:")
    print(f"   - В RU_WORDS: {correct_in_ru}")
    print(f"   - В EN_WORDS: {correct_in_en}")

    # Проверяем короткие слова
    if len(w) <= 2:
        print(f"7. КОРОТКОЕ СЛОВО (≤2 символа):")
        print(f"   - В SHORT_EN: {w in punto.SHORT_EN}")
        print(f"   - В SHORT_RU: {w in punto.SHORT_RU}")
        print(f"   - Конвертация в SHORT_EN: {punto.convert(w, 'en') in punto.SHORT_EN}")
        print(f"   - Конвертация в SHORT_RU: {punto.convert(w, 'ru') in punto.SHORT_RU}")

    # Диагноз
    print(f"\n{'─'*70}")
    print("ДИАГНОЗ:")

    if result == expected_lang:
        print("✅ Распознано правильно!")
    else:
        print("❌ НЕ РАСПОЗНАНО. Причины:")

        if expected_lang == "ru":
            if not ru_in_dict:
                print(f"   • Слово '{ru_variant}' ОТСУТСТВУЕТ в русском словаре")
                print(f"     (должно быть '{correct_lower}')")
        else:  # expected_lang == "en"
            if not en_in_dict:
                print(f"   • Слово '{en_variant}' ОТСУТСТВУЕТ в английском словаре")
                print(f"     (должно быть '{correct_lower}')")

        if len(w) <= 2:
            print(f"   • Слишком короткое слово — строгая проверка")

        if ru_variant != correct_lower and en_variant != correct_lower:
            print(f"   • Конвертация даёт неправильное слово:")
            print(f"     '{ru_variant}' вместо '{correct_lower}' или")
            print(f"     '{en_variant}' вместо '{correct_lower}'")

def main():
    print("\n" + "="*70)
    print("ДЕТАЛЬНЫЙ АНАЛИЗ ПРОБЛЕМ РАСПОЗНАВАНИЯ")
    print("="*70)

    punto = load_punto()

    # Проблемные слова из твоего сообщения
    failed_words = [
        ("цщклы", "en", "work"),
        ("crfxfpfnm", "ru", "сказать"),
        ("рщцуферук", "en", "however"),
        ("тще", "en", "too"),
        ("jcnfkztn", "ru", "остаётся"),
    ]

    for wrong, lang, correct in failed_words:
        analyze_word(punto, wrong, lang, correct)

    # Итоговые выводы
    print("\n" + "="*70)
    print("ОСНОВНЫЕ ПРОБЛЕМЫ:")
    print("="*70)
    print("""
1. ОПЕЧАТКИ В РАСКЛАДКЕ
   Пример: 'crfxfpfnm' → 'скачазать' вместо 'сказать'
   Причина: В русской раскладке 'з' и 'ж' на клавише 'p/з', но ты написал 'p'

2. СЛОВАРИ СОДЕРЖАТ ТОЛЬКО БАЗОВЫЕ ФОРМЫ
   Проблема: 'остаётся' → есть только 'оставаться'
   Решение: Нужны словари со всеми склонениями/спряжениями

3. НЕПРАВИЛЬНАЯ КОНВЕРТАЦИЯ
   Пример: 'цщклы' → 'works' вместо 'work'
   Причина: Конвертация побуквенная, не учитывает слово целиком

4. ОТСУТСТВИЕ СЛОВ В СЛОВАРЯХ
   Пример: 'however' отсутствует в словаре EN (93K слов слишком мало)

5. КОРОТКИЕ СЛОВА ИГНОРИРУЮТСЯ
   Пример: 'тще' → 'not' вместо 'too'
   Причина: Логика для коротких слов слишком строгая

РЕКОМЕНДАЦИИ ДЛЯ УЛУЧШЕНИЯ:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Расширить английский словарь до 200K+ слов
✓ Добавить словари с формами слов (не только базовые формы)
✓ Улучшить логику для коротких слов (2-3 символа)
✓ Добавить проверку опечаток (fuzzy matching)
✓ Использовать статистику частотности слов
""")

if __name__ == "__main__":
    main()
