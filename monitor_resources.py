#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мониторинг нагрузки punto на CPU и память
"""

import psutil
import time
import sys
import os

def format_bytes(bytes):
    """Форматирование байтов в читаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} TB"

def monitor_process(duration=10):
    """Мониторит процесс punto.py если он запущен"""
    print("\n" + "="*70)
    print("МОНИТОРИНГ НАГРУЗКИ PUNTO")
    print("="*70 + "\n")

    # Ищем процесс punto
    punto_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and any('punto' in str(arg).lower() for arg in cmdline):
                if 'python' in proc.info['name'].lower():
                    punto_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not punto_processes:
        print("⚠️  Процесс punto не запущен!")
        print("\nЗапустите punto.py и повторите мониторинг")
        print("\nПредварительная оценка (по коду):")
        print("  • Память при запуске: ~150-200 MB")
        print("  • CPU в режиме ожидания: ~0.1-0.5%")
        print("  • CPU при исправлении: ~5-15% (кратковременно)")
        return

    print(f"Найдено процессов punto: {len(punto_processes)}\n")

    for proc in punto_processes:
        print(f"📊 PID: {proc.pid} | {' '.join(proc.cmdline()[-2:])}")
        print("-"*70)

        samples = []
        try:
            # Начальные значения
            proc.cpu_percent(interval=None)  # Первый вызов для инициализации

            for i in range(duration):
                # Замеряем CPU и память
                cpu = proc.cpu_percent(interval=1)
                mem_info = proc.memory_info()
                mem_percent = proc.memory_percent()

                sample = {
                    'cpu': cpu,
                    'rss': mem_info.rss,
                    'vms': mem_info.vms,
                    'mem_percent': mem_percent
                }
                samples.append(sample)

                print(f"[{i+1:2d}/{duration}] CPU: {cpu:5.1f}% | "
                      f"RSS: {format_bytes(mem_info.rss):>10} | "
                      f"VMS: {format_bytes(mem_info.vms):>10} | "
                      f"MEM: {mem_percent:5.2f}%")

            # Статистика
            print("\n" + "-"*70)
            print("СТАТИСТИКА:")
            avg_cpu = sum(s['cpu'] for s in samples) / len(samples)
            max_cpu = max(s['cpu'] for s in samples)
            avg_rss = sum(s['rss'] for s in samples) / len(samples)
            max_rss = max(s['rss'] for s in samples)
            avg_mem = sum(s['mem_percent'] for s in samples) / len(samples)

            print(f"  CPU средний: {avg_cpu:.2f}%")
            print(f"  CPU максимум: {max_cpu:.2f}%")
            print(f"  RSS средний: {format_bytes(avg_rss)}")
            print(f"  RSS максимум: {format_bytes(max_rss)}")
            print(f"  Память средняя: {avg_mem:.2f}%")

            # Оценка
            print("\n💡 ОЦЕНКА:")
            if avg_cpu < 1:
                print("  ✅ CPU: Отлично (< 1%)")
            elif avg_cpu < 5:
                print("  ⚠️  CPU: Приемлемо (1-5%)")
            else:
                print("  ❌ CPU: Высокая нагрузка (> 5%)")

            if avg_rss < 100 * 1024 * 1024:
                print("  ✅ Память: Отлично (< 100 MB)")
            elif avg_rss < 200 * 1024 * 1024:
                print("  ⚠️  Память: Приемлемо (100-200 MB)")
            else:
                print("  ❌ Память: Высокое потребление (> 200 MB)")

        except psutil.NoSuchProcess:
            print("\n⚠️  Процесс завершился во время мониторинга")
        except Exception as e:
            print(f"\n❌ Ошибка мониторинга: {e}")

        print()

def analyze_dictionary_memory():
    """Анализ памяти, занимаемой словарями"""
    print("\n" + "="*70)
    print("АНАЛИЗ ПАМЯТИ СЛОВАРЕЙ")
    print("="*70 + "\n")

    import sys
    sys.path.insert(0, os.path.expanduser("~/punto"))

    try:
        # Загружаем словари
        import importlib.util
        spec = importlib.util.spec_from_file_location("punto",
                                                       os.path.expanduser("~/punto/punto.py"))
        punto = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(punto)

        # Размеры словарей
        en_size = sys.getsizeof(punto.EN_WORDS)
        ru_size = sys.getsizeof(punto.RU_WORDS)
        exc_size = sys.getsizeof(punto.EXCEPTIONS)

        print(f"Словарь EN_WORDS: {len(punto.EN_WORDS):,} слов → {format_bytes(en_size)}")
        print(f"Словарь RU_WORDS: {len(punto.RU_WORDS):,} слов → {format_bytes(ru_size)}")
        print(f"Словарь EXCEPTIONS: {len(punto.EXCEPTIONS):,} слов → {format_bytes(exc_size)}")
        print(f"\nОбщий размер словарей: {format_bytes(en_size + ru_size + exc_size)}")

        # Оценка для разных версий
        print("\n" + "-"*70)
        print("ОЦЕНКА ПАМЯТИ ДЛЯ РАЗНЫХ ВЕРСИЙ:")
        base_dict_mem = en_size + ru_size + exc_size

        versions = [
            ("punto.py", base_dict_mem, "Только словари"),
            ("punto_fast.py", base_dict_mem + 10_000 * 100, "Словари + LRU кэш 10K"),
            ("punto_ultimate.py", base_dict_mem + 100_000 * 100, "Словари + LRU кэш 100K"),
            ("punto_hybrid.py", base_dict_mem + 50_000 * 100, "Словари + LRU кэш 50K"),
        ]

        for name, estimated_mem, description in versions:
            print(f"  {name:20s} → ~{format_bytes(estimated_mem):>10} ({description})")

    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "dict":
        analyze_dictionary_memory()
    else:
        duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
        monitor_process(duration)
        print("\nДля анализа памяти словарей: python3 monitor_resources.py dict")
