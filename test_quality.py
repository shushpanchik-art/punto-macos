#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест качества распознавания punto на реальных словах
"""

import sys
import os
import importlib.util

PUNTO_DIR = os.path.expanduser("~/punto")
sys.path.insert(0, PUNTO_DIR)

# Реальные слова из твоего сообщения
TEST_CASES = [
    # (неправильно, правильный_язык, правильное_слово)
    ("еуые", "en", "test"),
    ("цщклы", "en", "work"),
    ("crfxfpfnm", "ru", "сказать"),
    ("ерфе", "en", "that"),
    ("рщцуферук", "en", "however"),
    ("тще", "en", "too"),
    ("[jhjij", "ru", "хорошо"),
    ("crjhjcnm", "ru", "скорость"),
    ("hf,jns", "ru", "работы"),
    ("jcnfkztn", "ru", "остаётся"),
    (";tkfnm", "ru", "желать"),
    ("kexituj", "ru", "лучшего"),
]

def load_punto():
    spec = importlib.util.spec_from_file_location("punto", os.path.join(PUNTO_DIR, "punto.py"))
    punto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(punto)
    return punto

def main():
    print("\n" + "="*70)
    print("ТЕСТ КАЧЕСТВА РАСПОЗНАВАНИЯ")
    print("="*70 + "\n")

    punto = load_punto()

    passed = 0
    failed = 0

    print(f"Английских слов в словаре: {len(punto.EN_WORDS):,}")
    print(f"Русских слов в словаре: {len(punto.RU_WORDS):,}\n")
    print("-"*70 + "\n")

    for wrong_word, expected_lang, correct_word in TEST_CASES:
        result_lang = punto.decide(wrong_word)

        if result_lang == expected_lang:
            converted = punto.convert(wrong_word, expected_lang)
            if converted == correct_word:
                print(f"✅ '{wrong_word}' → {expected_lang} → '{converted}'")
                passed += 1
            else:
                print(f"❌ '{wrong_word}' → {expected_lang} → '{converted}' (ожидалось '{correct_word}')")
                failed += 1
        else:
            # Проверим, есть ли слова в словарях
            wrong_lower = wrong_word.lower().replace("ё", "е")
            converted_ru = punto.convert(wrong_word, "ru").lower().replace("ё", "е")
            converted_en = punto.convert(wrong_word, "en").lower().replace("ё", "е")

            in_en = wrong_lower in punto.EN_WORDS
            in_ru = wrong_lower in punto.RU_WORDS
            target_en = converted_en in punto.EN_WORDS
            target_ru = converted_ru in punto.RU_WORDS

            print(f"❌ '{wrong_word}' → {result_lang} (ожидалось {expected_lang})")
            print(f"   Исходное в EN: {in_en}, в RU: {in_ru}")
            print(f"   Целевое '{converted_en}' в EN: {target_en}")
            print(f"   Целевое '{converted_ru}' в RU: {target_ru}")
            print(f"   Правильное: '{correct_word}'")
            failed += 1
        print()

    print("="*70)
    print(f"РЕЗУЛЬТАТ: {passed}/{passed+failed} слов распознано")
    print(f"Качество: {passed/(passed+failed)*100:.1f}%")
    print("="*70 + "\n")

    if failed > 0:
        print("🔍 ПРОБЛЕМЫ:")
        print("1. Многие слова отсутствуют в словарях")
        print("2. Словари содержат только базовые формы, нет склонений")
        print("3. Логика decide() слишком осторожна для коротких слов")
        print()

if __name__ == "__main__":
    main()
