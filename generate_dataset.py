#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор датасета для обучения микромодели коррекции раскладки

Создаёт пары: неправильный текст -> правильный текст
Например: "ghbdtn" -> "привет", "руддщ" -> "hello"
"""

import json
import random
from pathlib import Path

# Частые слова для обучения
RUSSIAN_WORDS = [
    "привет", "пока", "спасибо", "пожалуйста", "да", "нет",
    "работает", "не работает", "хорошо", "плохо", "отлично",
    "тестирую", "проверяю", "смотрю", "делаю", "понимаю",
    "сделать", "проверить", "посмотреть", "написать", "прочитать",
    "сегодня", "завтра", "вчера", "сейчас", "потом",
    "github", "python", "code", "test", "fix", "bug",
    "файл", "папка", "код", "тест", "ошибка", "баг",
    "как дела", "что делаешь", "все хорошо", "не работает",
    "исправить", "сломалось", "работает отлично",
]

ENGLISH_WORDS = [
    "hello", "goodbye", "thanks", "please", "yes", "no",
    "working", "not working", "good", "bad", "excellent",
    "testing", "checking", "looking", "doing", "understanding",
    "make", "check", "look", "write", "read",
    "today", "tomorrow", "yesterday", "now", "later",
    "github", "python", "code", "test", "fix", "bug",
    "file", "folder", "code", "test", "error", "bug",
    "how are you", "what are you doing", "all good", "not working",
    "fix it", "broken", "works great",
]

# Таблица конвертации EN -> RU
EN_TO_RU = str.maketrans(
    "qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?`~",
    "йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,ёЁ"
)

# Таблица конвертации RU -> EN
RU_TO_EN = str.maketrans(
    "йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,ёЁ",
    "qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?`~"
)


def convert_layout(text, target):
    """Конвертировать текст в другую раскладку"""
    if target == "ru":
        return text.translate(EN_TO_RU)
    else:
        return text.translate(RU_TO_EN)


def generate_training_examples(num_examples=10000):
    """Генерировать примеры для обучения"""
    examples = []

    # Русские слова набранные на английской раскладке
    for _ in range(num_examples // 4):
        word = random.choice(RUSSIAN_WORDS)
        wrong = convert_layout(word, "en")
        examples.append({
            "input": wrong,
            "output": word,
            "task": "ru_from_en"
        })

    # Английские слова набранные на русской раскладке
    for _ in range(num_examples // 4):
        word = random.choice(ENGLISH_WORDS)
        wrong = convert_layout(word, "ru")
        examples.append({
            "input": wrong,
            "output": word,
            "task": "en_from_ru"
        })

    # Короткие слова (критичный случай!)
    short_words_ru = ["да", "нет", "не", "на", "за", "из", "он", "она", "мы", "вы"]
    short_words_en = ["am", "is", "no", "ok", "hi", "me", "we", "he", "it", "do"]

    for word in short_words_ru:
        wrong = convert_layout(word, "en")
        examples.append({
            "input": wrong,
            "output": word,
            "task": "ru_from_en_short"
        })

    for word in short_words_en:
        wrong = convert_layout(word, "ru")
        examples.append({
            "input": wrong,
            "output": word,
            "task": "en_from_ru_short"
        })

    # Предложения (контекстное обучение)
    sentences_ru = [
        "привет как дела",
        "все работает отлично",
        "нужно исправить баг",
        "проверяю код сейчас",
        "написал тест для этого",
    ]

    sentences_en = [
        "hello how are you",
        "everything works great",
        "need to fix the bug",
        "checking code now",
        "wrote test for this",
    ]

    for sentence in sentences_ru:
        wrong = convert_layout(sentence, "en")
        examples.append({
            "input": wrong,
            "output": sentence,
            "task": "ru_sentence"
        })

    for sentence in sentences_en:
        wrong = convert_layout(sentence, "ru")
        examples.append({
            "input": wrong,
            "output": sentence,
            "task": "en_sentence"
        })

    # Перемешиваем
    random.shuffle(examples)

    return examples


def main():
    """Создать датасет"""
    print("🔥 Генерирую датасет для обучения микромодели...")

    examples = generate_training_examples(10000)

    # Разделяем на train/val
    split = int(len(examples) * 0.9)
    train_examples = examples[:split]
    val_examples = examples[split:]

    # Сохраняем
    dataset_dir = Path("punto_dataset")
    dataset_dir.mkdir(exist_ok=True)

    with open(dataset_dir / "train.jsonl", "w", encoding="utf-8") as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(dataset_dir / "val.jsonl", "w", encoding="utf-8") as f:
        for ex in val_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"✅ Создано {len(train_examples)} train примеров")
    print(f"✅ Создано {len(val_examples)} val примеров")
    print(f"📁 Сохранено в {dataset_dir}/")

    # Покажем примеры
    print("\n📊 Примеры из датасета:")
    for ex in train_examples[:5]:
        print(f"  {ex['input']:20} → {ex['output']:20} [{ex['task']}]")


if __name__ == "__main__":
    main()
