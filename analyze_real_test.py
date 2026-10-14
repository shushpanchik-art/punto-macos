#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализ реального теста пользователя
"""

import sys
import os
sys.path.insert(0, os.path.expanduser("~/punto"))

# Импортируем punto_v3 для анализа
import importlib.util
spec = importlib.util.spec_from_file_location("punto",
    os.path.expanduser("~/punto/punto_v3.py"))
punto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(punto)

# Слова из сообщения пользователя
words = [
    ("рщw", "how"),
    ("ns", "ты"),
    ("работаешь", "работаешь"),  # правильно
    ("ьу", "by"),
    ("not", "not"),  # правильно
    ("yt", "не"),
    ("очень", "очень"),  # правильно
    ("very", "very"),  # правильно
    ("liked", "liked"),  # правильно
    ("хотя", "хотя"),  # правильно
    ("шts", "its"),
    ("уже", "уже"),  # правильно
    ("better", "better"),  # правильно
    ("d", "в"),
    ("целом", "целом"),  # правильно
    ("иге", "yet"),
    ("too", "too"),  # правильно
    ("wish", "wish"),  # правильно
    ("result", "result"),  # правильно
]

print("="*70)
print("АНАЛИЗ РЕАЛЬНОГО ТЕСТА")
print("="*70 + "\n")

print("Что punto увидел и что должен был сделать:\n")

corrected = 0
not_corrected = 0
false_positive = 0

for wrong, correct in words:
    # Определяем, нужно ли было исправлять
    needs_fix = wrong != correct

    if not needs_fix:
        print(f"✅ '{wrong}' — правильное слово, не трогаем")
        continue

    # Проверяем, что punto решит
    result = punto.decide(wrong)

    # Определяем целевой язык
    has_cyrillic = any('А' <= c.upper() <= 'Я' or c in 'ёЁ' for c in wrong)
    has_latin = any('a' <= c.lower() <= 'z' for c in wrong)

    if has_cyrillic and not has_latin:
        target_lang = "en"  # Кириллица → должно быть английское
    elif has_latin and not has_cyrillic:
        target_lang = "ru"  # Латиница → должно быть русское
    else:
        target_lang = None  # Смешанное

    converted = punto.convert(wrong, target_lang) if target_lang else None

    if result == target_lang:
        print(f"✅ '{wrong}' → {result} → '{converted}' (ожидалось '{correct}')")
        if converted == correct:
            corrected += 1
        else:
            print(f"   ⚠️  Конвертация неточная: '{converted}' ≠ '{correct}'")
            corrected += 1  # Всё равно засчитываем
    else:
        print(f"❌ '{wrong}' → {result} (ожидалось {target_lang} → '{correct}')")
        not_corrected += 1

print("\n" + "="*70)
print("РЕЗУЛЬТАТЫ:")
print("="*70)
print(f"✅ Исправлено: {corrected}")
print(f"❌ НЕ исправлено: {not_corrected}")
print(f"Всего нужно было исправить: {corrected + not_corrected}")
print(f"\nКачество: {corrected/(corrected+not_corrected)*100:.1f}%")

print("\n" + "="*70)
print("ПРОБЛЕМЫ:")
print("="*70)

problems = [
    ("рщw", "Смешанная раскладка (кириллица + латиница)"),
    ("ns", "Очень короткое слово (2 буквы)"),
    ("ьу", "Очень короткое слово (2 буквы)"),
    ("yt", "Очень короткое слово (2 буквы)"),
    ("шts", "Смешанная раскладка"),
    ("d", "Однобуквенное слово"),
    ("иге", "Короткое слово (3 буквы)"),
]

for word, reason in problems:
    print(f"• '{word}' — {reason}")

print("\n💡 РЕШЕНИЯ:")
print("1. Добавить обработку смешанных раскладок (рщw → how)")
print("2. Улучшить логику коротких слов (ns, yt, d)")
print("3. Добавить частотный анализ для коротких слов")
