#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборщик статистики n-грамм из словарей
Создает базы данных биграмм и триграмм для русского и английского языков
"""

import json
import os
from collections import defaultdict, Counter

def load_words(filename):
    """Загружает словарь из файла"""
    words = []
    with open(filename, encoding='utf-8') as f:
        for line in f:
            word = line.strip().lower().replace('ё', 'е')
            if word and len(word) >= 2:  # Минимум 2 буквы
                words.append(word)
    return words

def collect_bigrams(words):
    """Собирает статистику биграмм (2 буквы)"""
    bigrams = Counter()
    total = 0

    for word in words:
        for i in range(len(word) - 1):
            bigram = word[i:i+2]
            bigrams[bigram] += 1
            total += 1

    # Нормализуем (вероятности)
    bigram_probs = {}
    for bigram, count in bigrams.items():
        bigram_probs[bigram] = count / total

    return bigram_probs

def collect_trigrams(words):
    """Собирает статистику триграмм (3 буквы)"""
    trigrams = Counter()
    total = 0

    for word in words:
        for i in range(len(word) - 2):
            trigram = word[i:i+3]
            trigrams[trigram] += 1
            total += 1

    # Нормализуем
    trigram_probs = {}
    for trigram, count in trigrams.items():
        trigram_probs[trigram] = count / total

    return trigram_probs

def collect_initial_letters(words):
    """Собирает статистику начальных букв"""
    initials = Counter()

    for word in words:
        if word:
            initials[word[0]] += 1

    total = len(words)
    initial_probs = {}
    for letter, count in initials.items():
        initial_probs[letter] = count / total

    return initial_probs

def collect_impossible_combinations(words, lang):
    """Определяет невозможные/очень редкие сочетания"""
    all_bigrams = set()
    all_trigrams = set()

    # Собираем все возможные сочетания
    for word in words:
        for i in range(len(word) - 1):
            all_bigrams.add(word[i:i+2])
        for i in range(len(word) - 2):
            all_trigrams.add(word[i:i+3])

    # Определяем алфавит
    if lang == 'ru':
        alphabet = set('абвгдежзийклмнопрстуфхцчшщъыьэюя')
    else:
        alphabet = set('abcdefghijklmnopqrstuvwxyz')

    # Невозможные биграммы (отсутствующие во всех словах)
    impossible_bigrams = []
    for a in alphabet:
        for b in alphabet:
            bigram = a + b
            if bigram not in all_bigrams:
                impossible_bigrams.append(bigram)

    return {
        'impossible_bigrams': impossible_bigrams[:100],  # Топ-100 самых невозможных
        'total_bigrams': len(all_bigrams),
        'total_trigrams': len(all_trigrams)
    }

def main():
    print("="*70)
    print("СБОРЩИК СТАТИСТИКИ N-ГРАММ")
    print("="*70 + "\n")

    here = os.path.dirname(os.path.abspath(__file__))

    # Обрабатываем русский язык
    print("📊 Обработка русского языка...")
    ru_words = load_words(os.path.join(here, "words_ru.txt"))
    print(f"   Загружено слов: {len(ru_words):,}")

    print("   Собираем биграммы...")
    ru_bigrams = collect_bigrams(ru_words)
    print(f"   Найдено уникальных биграмм: {len(ru_bigrams):,}")

    print("   Собираем триграммы...")
    ru_trigrams = collect_trigrams(ru_words)
    print(f"   Найдено уникальных триграмм: {len(ru_trigrams):,}")

    print("   Собираем начальные буквы...")
    ru_initials = collect_initial_letters(ru_words)
    print(f"   Найдено уникальных начальных букв: {len(ru_initials)}")

    print("   Определяем невозможные сочетания...")
    ru_impossible = collect_impossible_combinations(ru_words, 'ru')
    print(f"   Невозможных биграмм: {len(ru_impossible['impossible_bigrams'])}")

    # Сохраняем русский
    print("   Сохранение в файлы...")
    with open(os.path.join(here, "ngrams_ru.json"), 'w', encoding='utf-8') as f:
        json.dump({
            'bigrams': ru_bigrams,
            'trigrams': ru_trigrams,
            'initials': ru_initials,
            'impossible': ru_impossible
        }, f, ensure_ascii=False, indent=2)

    # Обрабатываем английский язык
    print("\n📊 Обработка английского языка...")
    en_words = load_words(os.path.join(here, "words_en.txt"))
    print(f"   Загружено слов: {len(en_words):,}")

    print("   Собираем биграммы...")
    en_bigrams = collect_bigrams(en_words)
    print(f"   Найдено уникальных биграмм: {len(en_bigrams):,}")

    print("   Собираем триграммы...")
    en_trigrams = collect_trigrams(en_words)
    print(f"   Найдено уникальных триграмм: {len(en_trigrams):,}")

    print("   Собираем начальные буквы...")
    en_initials = collect_initial_letters(en_words)
    print(f"   Найдено уникальных начальных букв: {len(en_initials)}")

    print("   Определяем невозможные сочетания...")
    en_impossible = collect_impossible_combinations(en_words, 'en')
    print(f"   Невозможных биграмм: {len(en_impossible['impossible_bigrams'])}")

    # Сохраняем английский
    print("   Сохранение в файлы...")
    with open(os.path.join(here, "ngrams_en.json"), 'w', encoding='utf-8') as f:
        json.dump({
            'bigrams': en_bigrams,
            'trigrams': en_trigrams,
            'initials': en_initials,
            'impossible': en_impossible
        }, f, ensure_ascii=False, indent=2)

    # Итоговая статистика
    print("\n" + "="*70)
    print("РЕЗУЛЬТАТЫ:")
    print("="*70)
    print("\n                     Русский      Английский")
    print("-"*70)
    print(f"Слов:               {len(ru_words):>8,}    {len(en_words):>10,}")
    print(f"Биграмм:            {len(ru_bigrams):>8,}    {len(en_bigrams):>10,}")
    print(f"Триграмм:           {len(ru_trigrams):>8,}    {len(en_trigrams):>10,}")
    print(f"Начальных букв:     {len(ru_initials):>8}    {len(en_initials):>10}")

    # Примеры самых частых биграмм
    print("\n" + "="*70)
    print("ТОП-10 САМЫХ ЧАСТЫХ БИГРАММ:")
    print("="*70)

    print("\n🇷🇺 Русский:")
    top_ru = sorted(ru_bigrams.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (bigram, prob) in enumerate(top_ru, 1):
        print(f"   {i:2d}. '{bigram}' — {prob*100:.2f}%")

    print("\n🇬🇧 Английский:")
    top_en = sorted(en_bigrams.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (bigram, prob) in enumerate(top_en, 1):
        print(f"   {i:2d}. '{bigram}' — {prob*100:.2f}%")

    # Примеры невозможных сочетаний
    print("\n" + "="*70)
    print("ПРИМЕРЫ НЕВОЗМОЖНЫХ БИГРАММ:")
    print("="*70)
    print(f"\n🇷🇺 Русский (первые 20): {', '.join(ru_impossible['impossible_bigrams'][:20])}")
    print(f"\n🇬🇧 Английский (первые 20): {', '.join(en_impossible['impossible_bigrams'][:20])}")

    print("\n✅ Готово! Файлы сохранены:")
    print("   - ngrams_ru.json")
    print("   - ngrams_en.json")
    print()

if __name__ == "__main__":
    main()
