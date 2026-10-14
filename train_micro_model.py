#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обучение микромодели для коррекции раскладки через Unsloth

Цель: Создать tiny transformer модель (< 50MB) для быстрой коррекции раскладки
"""

import json
from pathlib import Path
from unsloth import FastLanguageModel
from datasets import load_dataset
import torch

# Конфигурация модели
MAX_SEQ_LENGTH = 64  # Короткие тексты
MODEL_NAME = "unsloth/Qwen2.5-0.5B-Instruct"  # Tiny модель 500M параметров
LORA_R = 8  # Ранг LoRA
LORA_ALPHA = 16

def format_prompt(example):
    """Форматировать пример для обучения"""
    instruction = "Fix the keyboard layout: convert the text from wrong layout to correct one."
    input_text = example["input"]
    output_text = example["output"]

    return {
        "text": f"""Below is an instruction that describes a task. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input_text}

### Response:
{output_text}"""
    }

def main():
    print("🔥 Начинаю обучение микромодели через Unsloth...")

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

    # 2. Форматируем датасет
    print("\n🔧 Форматирую датасет...")
    dataset = dataset.map(format_prompt)

    # 3. Загружаем базовую модель
    print(f"\n🤖 Загружаю модель {MODEL_NAME}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,  # Auto detect
        load_in_4bit=True,  # Квантизация для экономии памяти
    )

    # 4. Добавляем LoRA адаптеры
    print("\n⚙️ Настраиваю LoRA адаптеры...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
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
            per_device_train_batch_size=8,
            gradient_accumulation_steps=4,
            warmup_steps=10,
            max_steps=200,  # Быстрое обучение
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir="punto_model_output",
            eval_strategy="steps",
            eval_steps=50,
            save_strategy="steps",
            save_steps=100,
            save_total_limit=2,
        ),
    )

    # 6. Обучаем!
    print("\n🚀 Начинаю обучение...")
    trainer_stats = trainer.train()

    # 7. Сохраняем модель
    print("\n💾 Сохраняю модель...")

    # Сохраняем в формате GGUF (компактный)
    model.save_pretrained_gguf(
        "punto_micro_model",
        tokenizer,
        quantization_method="q4_k_m"  # 4-bit квантизация
    )

    print("\n✅ Обучение завершено!")
    print(f"📁 Модель сохранена в punto_micro_model/")
    print(f"📊 Статистика: {trainer_stats}")

    # 8. Тестируем модель
    print("\n🧪 Тестирую модель...")
    test_inputs = [
        "ghbdtn",  # привет
        "руддщ",   # hello
        "hf,jnftn", # работает
        "цщклштп",  # working
        "lf",      # да
        "тщ",      # no
    ]

    FastLanguageModel.for_inference(model)

    for inp in test_inputs:
        prompt = f"""Below is an instruction that describes a task. Write a response that appropriately completes the request.

### Instruction:
Fix the keyboard layout: convert the text from wrong layout to correct one.

### Input:
{inp}

### Response:
"""
        inputs = tokenizer([prompt], return_tensors="pt").to("cuda")
        outputs = model.generate(
            **inputs,
            max_new_tokens=32,
            use_cache=True,
            temperature=0.1,
        )
        result = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Извлекаем только ответ
        response = result.split("### Response:")[-1].strip()
        print(f"  {inp:15} → {response}")

    print("\n🎉 Готово! Микромодель обучена и готова к использованию!")

if __name__ == "__main__":
    main()
