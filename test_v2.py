#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест punto_v2 с fuzzy matching
"""

import sys
import os
import importlib.util

PUNTO_DIR = os.path.expanduser("~/punto")
sys.path.insert(0, PUNTO_DIR)

def load_punto_v2():
    spec = importlib.util.spec_from_file_location("punto_v2", os.path.join(PUNTO_DIR, "punto_v2.py"))
    punto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(punto)
    return punto

def main():
    print("\n" + "="*70)
    print("ТЕСТ PUNTO V2 С FUZZY MATCHING")
    print("="*70 + "\n")

    punto = load_punto_v2()

    # Те же слова из твоего сообщения
    TEST_CASES = [
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

    passed = 0
    failed = 0

    for wrong_word, expected_lang, correct_word in TEST_CASES:
        result_lang = punto.decide(wrong_word)

        if result_lang == expected_lang:
            converted = punto.convert(wrong_word, expected_lang)
            print(f"✅ '{wrong_word}' → {expected_lang} → '{converted}' (ожидалось '{correct_word}')")
            passed += 1
        else:
            print(f"❌ '{wrong_word}' → {result_lang} (ожидалось {expected_lang} → '{correct_word}')")
            failed += 1

    print("\n" + "="*70)
    print(f"РЕЗУЛЬТАТ: {passed}/{passed+failed} слов распознано")
    improvement = passed / (passed + failed) * 100
    print(f"Качество: {improvement:.1f}%")

    # Сравнение с оригиналом
    original_quality = 58.3
    print(f"\nБыло: {original_quality:.1f}%")
    print(f"Стало: {improvement:.1f}%")
    if improvement > original_quality:
        print(f"📈 Улучшение: +{improvement - original_quality:.1f}%")

    print("="*70 + "\n")

if __name__ == "__main__":
    main()
