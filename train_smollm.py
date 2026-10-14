#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обучение МИКРО-модели SmolLM-135M для коррекции раскладки

SmolLM-135M: 135 миллионов параметров → ~50-70MB после квантизации
"""

import json
from pathlib import Path
from unsloth import FastLanguageModel
from datasets import load_dataset
import torch

# Конфигурация МИКРО-модели
MAX_SEQ_LENGTH = 32  # Очень короткие тексты (одно слово)
MODEL_NAME = "HuggingFaceTB/SmolLM-135M"  # МИКРО модель!
LORA_R = 4  # Меньший ранг LoRA для tiny модели
LORA_ALPHA = 8

def format_prompt(example):
    """Форматировать пример - ОЧЕНЬ ПРОСТОЙ промпт"""
    input_text = example["input"]
    output_text = example["output"]

    # Минималистичный промпт - просто input → output
    return {
        "text": f"Convert: {input_text}\nResult: {output_text}"
    }

def main():
    print("🔥 Обучаю МИКРО-модель SmolLM-135M...")

    # 1. Загружаем датасет
    print("\n📦 Загружаю датасет...")
    dataset = load_dataset(
        "json",
        data_files={
            "train": "punto_dataset/train.jsonl",
            "validation": "punto_dataset/val.jsonl"
        }
    )

    print(f"  Train: {len(dataset['train'])} примеров")
    print(f"  Val: {len(dataset['validation'])} примеров")

    # 2. Форматируем датасет (простой формат!)
    print("\n🔧 Форматирую датасет...")
    dataset = dataset.map(format_prompt)

    # 3. Загружаем МИКРО модель
    print(f"\n🤖 Загружаю модель {MODEL_NAME}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )

    # 4. Добавляем LoRA
    print("\n⚙️ Настраиваю LoRA (меньший ранг для tiny модели)...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,  # Меньше для tiny модели
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                       "gate_proj", "up_proj", "down_proj"],
        lora_alpha=LORA_ALPHA,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # 5. Настраиваем тренер
    print("\n🏃 Настраиваю тренер...")
    from transformers import TrainingArguments
    from trl import SFTTrainer

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=4,
        args=TrainingArguments(
            per_device_train_batch_size=16,  # Больше batch для tiny модели
            gradient_accumulation_steps=2,
            warmup_steps=10,
            max_steps=300,  # Больше шагов для лучшего качества
            learning_rate=3e-4,  # Выше LR для tiny модели
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir="smollm_punto_output",
            eval_strategy="steps",
            eval_steps=50,
            save_strategy="steps",
            save_steps=150,
            save_total_limit=2,
        ),
    )

    # 6. Обучаем!
    print("\n🚀 Начинаю обучение...")
    trainer_stats = trainer.train()

    # 7. Сохраняем модель
    print("\n💾 Сохраняю модель...")

    # Сохраняем в GGUF (самый компактный формат)
    model.save_pretrained_gguf(
        "punto_smollm_micro",
        tokenizer,
        quantization_method="q4_k_m"  # 4-bit квантизация
    )

    print("\n✅ Обучение завершено!")
    print(f"📁 Модель сохранена в punto_smollm_micro/")
    print(f"📊 Статистика: {trainer_stats}")

    # 8. Тестируем модель
    print("\n🧪 Тестирую МИКРО-модель...")
    test_cases = [
        "ghbdtn",   # привет
        "руддщ",    # hello
        "hf,jnftn", # работает
        "цщклштп",  # working
        "lf",       # да
        "тщ",       # no
        "rfr ltkf", # как дела
    ]

    FastLanguageModel.for_inference(model)

    for inp in test_cases:
        prompt = f"Convert: {inp}\nResult: "
        inputs = tokenizer([prompt], return_tensors="pt").to("cuda")
        outputs = model.generate(
            **inputs,
            max_new_tokens=16,  # Короткие ответы
            use_cache=True,
            temperature=0.1,
            do_sample=False,  # Жадный decode
        )
        result = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Извлекаем только ответ
        response = result.split("Result: ")[-1].strip().split()[0] if "Result: " in result else result.strip()
        print(f"  {inp:15} → {response}")

    # Проверяем размер
    import os
    model_size = os.path.getsize("punto_smollm_micro/SmolLM-135M.Q4_K_M.gguf") / 1024 / 1024
    print(f"\n📦 Размер модели: {model_size:.1f}MB")

    print("\n🎉 МИКРО-модель готова!")

if __name__ == "__main__":
    main()
