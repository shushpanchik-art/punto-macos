#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Punto v5 - обработка смешанных раскладок + улучшенные короткие слова
Комбинирует fuzzy matching (v3) + n-граммы (v4) + новые эвристики
"""

import os
import queue
import sys
import threading
import time
import traceback
import json
from datetime import datetime
from functools import lru_cache
from collections import defaultdict

# Скрываем иконку приложения из дока
try:
    from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)
except Exception:
    pass

import objc
from Foundation import NSBundle
from pynput import keyboard
from pynput.keyboard import Key, Controller

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "punto.log")
DOUBLE_SHIFT_SEC = 0.4

# Настройки
FUZZY_MAX_DISTANCE = 2
FUZZY_MIN_WORD_LENGTH = 4


def log(msg):
    """Пишем только в файл."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    if sys.stdout.isatty():
        print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Системные функции переключения раскладки (HIToolbox)
# ---------------------------------------------------------------------------
_HITB = NSBundle.bundleWithPath_(
    "/System/Library/Frameworks/Carbon.framework/Frameworks/HIToolbox.framework"
)
_ns = {}
objc.loadBundleFunctions(
    _HITB,
    _ns,
    [
        ("TISCopyCurrentKeyboardInputSource", b"@"),
        ("TISCreateInputSourceList", b"@@Z"),
        ("TISSelectInputSource", b"i@"),
        ("TISGetInputSourceProperty", b"@@@"),
    ],
)
objc.loadBundleVariables(_HITB, _ns, [("kTISPropertyInputSourceID", b"@")])
TISCopyCurrentKeyboardInputSource = _ns["TISCopyCurrentKeyboardInputSource"]
TISCreateInputSourceList = _ns["TISCreateInputSourceList"]
TISSelectInputSource = _ns["TISSelectInputSource"]
TISGetInputSourceProperty = _ns["TISGetInputSourceProperty"]
kTISPropertyInputSourceID = _ns["kTISPropertyInputSourceID"]


def _source_id(src):
    return str(TISGetInputSourceProperty(src, kTISPropertyInputSourceID))


def current_layout():
    """'ru' если сейчас русская раскладка, иначе 'en'."""
    return "ru" if "Russian" in _source_id(TISCopyCurrentKeyboardInputSource()) else "en"


def switch_layout(lang):
    """Переключает раскладку на 'en' или 'ru'."""
    for src in TISCreateInputSourceList(None, False):
        sid = _source_id(src)
        if lang == "ru" and "Russian" in sid:
            TISSelectInputSource(src)
            return True
        if lang == "en" and ("keylayout.US" in sid or "ABC" in sid or "British" in sid):
            TISSelectInputSource(src)
            return True
    log(f"[!] Не найдена раскладка для '{lang}'")
    return False


# ---------------------------------------------------------------------------
# Соответствие клавиш EN <-> RU
# ---------------------------------------------------------------------------
EN_LOWER = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`"
RU_LOWER = "йцукенгшщзхъфывапролджэячсмитьбю.ё"
EN_UPPER = 'QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?~'
RU_UPPER = "ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,Ё"

TO_RU = dict(zip(EN_LOWER + EN_UPPER, RU_LOWER + RU_UPPER))
TO_EN = dict(zip(RU_LOWER + RU_UPPER, EN_LOWER + EN_UPPER))


def convert(text, to_lang):
    table = TO_RU if to_lang == "ru" else TO_EN
    return "".join(table.get(ch, ch) for ch in text)


# ---------------------------------------------------------------------------
# Расстояние Левенштейна для fuzzy matching
# ---------------------------------------------------------------------------
@lru_cache(maxsize=10000)
def levenshtein_distance(s1, s2):
    """Вычисляет расстояние Левенштейна между двумя строками"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


# ---------------------------------------------------------------------------
# Загрузка данных
# ---------------------------------------------------------------------------
def load_words(filename, fallback):
    path = os.path.join(HERE, filename)
    try:
        with open(path, encoding="utf-8") as f:
            words = {line.strip().lower().replace("ё", "е") for line in f if line.strip()}
        log(f"Загружен словарь {filename}: {len(words)} слов")
        return words
    except OSError:
        log(f"[!] Не найден {filename}, использую короткий встроенный список")
        return set(fallback.split())


def load_exceptions(filename):
    path = os.path.join(HERE, filename)
    try:
        with open(path, encoding="utf-8") as f:
            words = {line.strip().lower().replace("ё", "е") for line in f
                     if line.strip() and not line.startswith("#")}
        log(f"Загружены исключения {filename}: {len(words)} слов")
        return words
    except OSError:
        log(f"Файл {filename} не найден, исключений нет")
        return set()


def load_ngrams(lang):
    """Загружает n-граммы для языка"""
    filename = f"ngrams_{lang}.json"
    path = os.path.join(HERE, filename)
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        log(f"Загружены n-граммы {filename}: "
            f"{len(data['bigrams'])} биграмм, {len(data['trigrams'])} триграмм")
        return data
    except OSError:
        log(f"[!] Не найден {filename}, статистический анализ недоступен")
        return None


def build_prefix_index(words, prefix_len=2):
    """Строит индекс по первым буквам для быстрого поиска"""
    index = defaultdict(list)
    for word in words:
        if len(word) >= prefix_len:
            prefix = word[:prefix_len]
            index[prefix].append(word)
    log(f"Построен индекс префиксов: {len(index)} групп")
    return index


EN_WORDS = load_words(
    "words_en.txt",
    "the and you that have for not with this but from they we say hello thanks "
    "please yes hi ok world code good night morning however too weather by yet",
)
RU_WORDS = load_words(
    "words_ru.txt",
    "и в не на что он я с как а то все она так его но да ты к у же вы за "
    "привет спасибо пожалуйста работа сегодня просто время остается сказать",
)
EXCEPTIONS = load_exceptions("exceptions.txt")

# Строим индексы
EN_PREFIX_INDEX = build_prefix_index(EN_WORDS, prefix_len=2)
RU_PREFIX_INDEX = build_prefix_index(RU_WORDS, prefix_len=2)

# Загружаем n-граммы
NGRAMS_RU = load_ngrams('ru')
NGRAMS_EN = load_ngrams('en')

# Короткие слова из 2 букв + частые 3-буквенные
SHORT_EN = {"am", "an", "as", "at", "be", "by", "do", "go", "he", "hi", "if", "in",
            "is", "it", "me", "my", "no", "of", "ok", "on", "or", "so", "to", "up",
            "us", "we", "you", "the", "and", "not", "but", "for", "are", "was", "all",
            "can", "had", "her", "his", "one", "our", "out", "day", "get", "has", "him",
            "how", "its", "may", "new", "now", "old", "see", "two", "way", "who", "boy",
            "did", "car", "let", "put", "say", "she", "too", "use", "yet"}
SHORT_RU = {"ам", "ах", "ба", "бы", "ва", "во", "да", "до", "ее", "ей", "ем", "ею",
            "её", "же", "за", "из", "им", "их", "ко", "ли", "мы", "на", "не", "ни",
            "но", "ну", "об", "ой", "он", "от", "по", "ра", "са", "се", "си", "со",
            "та", "те", "ти", "то", "ту", "ты", "уж", "ух", "эй", "эх", "юг", "юз",
            "як", "ям", "все", "для", "еще", "или", "как", "мне", "нас", "них", "нет",
            "она", "они", "оно", "при", "раз", "сам", "там", "уже", "это", "эти"}


# ---------------------------------------------------------------------------
# НОВОЕ: Обработка смешанных раскладок
# ---------------------------------------------------------------------------
def split_mixed_layout(word):
    """
    Разделяет слово на части по раскладкам
    Возвращает список кортежей (часть, язык)
    """
    if not word:
        return []

    parts = []
    current_part = word[0]
    current_lang = 'ru' if ('А' <= word[0].upper() <= 'Я' or word[0] in 'ёЁ') else 'en'

    for char in word[1:]:
        char_lang = 'ru' if ('А' <= char.upper() <= 'Я' or char in 'ёЁ') else 'en'

        if char_lang == current_lang:
            current_part += char
        else:
            parts.append((current_part, current_lang))
            current_part = char
            current_lang = char_lang

    parts.append((current_part, current_lang))
    return parts


def handle_mixed_layout(word):
    """
    Обрабатывает слово со смешанной раскладкой
    Возвращает (целевой_язык, конвертированное_слово) или (None, None)
    """
    parts = split_mixed_layout(word)

    if len(parts) == 1:
        return None, None  # Не смешанная раскладка

    # Считаем преобладающий язык по количеству букв
    ru_count = sum(len(part) for part, lang in parts if lang == 'ru')
    en_count = sum(len(part) for part, lang in parts if lang == 'en')

    # Определяем целевой язык (противоположный преобладающему)
    if ru_count > en_count:
        target = 'en'
        # Конвертируем русскую часть в английский
        converted = ''.join(
            convert(part, 'en') if lang == 'ru' else part
            for part, lang in parts
        )
    else:
        target = 'ru'
        # Конвертируем английскую часть в русский
        converted = ''.join(
            convert(part, 'ru') if lang == 'en' else part
            for part, lang in parts
        )

    log(f"[Mixed] '{word}' → {target}: '{converted}' (ru:{ru_count}, en:{en_count})")
    return target, converted


# ---------------------------------------------------------------------------
# НОВОЕ: Улучшенная работа с короткими словами через n-граммы
# ---------------------------------------------------------------------------
@lru_cache(maxsize=5000)
def word_probability(word, lang):
    """Вычисляет вероятность слова на основе n-грамм"""
    if len(word) < 2:
        return -100

    ngrams = NGRAMS_RU if lang == 'ru' else NGRAMS_EN
    if not ngrams:
        return -100

    score = 0.0

    # Начальная буква
    initial = word[0]
    initial_prob = ngrams['initials'].get(initial, 0.0001)
    score += 10 * initial_prob

    # Биграммы
    for i in range(len(word) - 1):
        bigram = word[i:i+2]
        bigram_prob = ngrams['bigrams'].get(bigram, 0.0)

        if bigram_prob == 0.0:
            score -= 20  # Невозможная биграмма
        else:
            score += 100 * bigram_prob

    # Триграммы (если есть)
    if len(word) >= 3:
        for i in range(len(word) - 2):
            trigram = word[i:i+3]
            trigram_prob = ngrams['trigrams'].get(trigram, 0.0)

            if trigram_prob > 0.0:
                score += 50 * trigram_prob
            else:
                score -= 5

    return score


# Кэш для fuzzy matching
_fuzzy_cache = {}


def find_closest_word_fast(word, lang):
    """Оптимизированный fuzzy search с индексом префиксов"""
    if len(word) < FUZZY_MIN_WORD_LENGTH:
        return None

    cache_key = (word, lang)
    if cache_key in _fuzzy_cache:
        return _fuzzy_cache[cache_key]

    if lang == "ru":
        prefix_index = RU_PREFIX_INDEX
        full_dict = RU_WORDS
    else:
        prefix_index = EN_PREFIX_INDEX
        full_dict = EN_WORDS

    prefix = word[:2]
    candidates = set()

    # Точный префикс
    if prefix in prefix_index:
        candidates.update(prefix_index[prefix])

    # Похожие префиксы
    for pref in prefix_index:
        if abs(len(pref) - len(prefix)) <= 1:
            if pref == prefix or levenshtein_distance(pref, prefix) <= 1:
                candidates.update(prefix_index[pref])

    # Добавляем слова похожей длины
    if len(candidates) < 50:
        target_len = len(word)
        for dict_word in full_dict:
            if abs(len(dict_word) - target_len) <= FUZZY_MAX_DISTANCE:
                candidates.add(dict_word)
                if len(candidates) >= 100:
                    break

    # Ищем лучшее совпадение
    best_match = None
    best_distance = FUZZY_MAX_DISTANCE + 1

    for candidate in candidates:
        distance = levenshtein_distance(word, candidate)
        if distance < best_distance:
            best_distance = distance
            best_match = candidate

            if distance == 0:
                break

    result = best_match if best_distance <= FUZZY_MAX_DISTANCE else None

    if len(_fuzzy_cache) > 5000:
        _fuzzy_cache.clear()

    _fuzzy_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Главная функция распознавания
# ---------------------------------------------------------------------------
def decide(word):
    """
    Возвращает язык, на который надо исправить слово, или None.
    v5: обработка смешанных раскладок + улучшенные короткие слова
    """
    w = word.lower().replace("ё", "е")
    if w in EXCEPTIONS:
        return None

    # Определяем язык по символам в слове
    has_cyrillic = any('а' <= c <= 'я' or c == 'ё' for c in w)
    has_latin = any('a' <= c <= 'z' for c in w)

    # НОВОЕ: Обработка смешанных раскладок
    if has_cyrillic and has_latin:
        target, converted = handle_mixed_layout(word)
        if target:
            return target

    # Для коротких слов (1-3 символа) — улучшенная проверка
    if len(w) <= 3:
        # Проверяем в расширенных списках коротких слов
        if w in SHORT_EN or w in SHORT_RU:
            return None

        # Конвертируем
        ru_variant = convert(w, "ru").replace("ё", "е")
        en_variant = convert(w, "en")

        # Проверяем конвертированные
        if has_latin and not has_cyrillic:
            if ru_variant in SHORT_RU or ru_variant in RU_WORDS:
                log(f"[Short] '{w}' → ru: '{ru_variant}' найдено")
                return "ru"

            # НОВОЕ: Проверяем через n-граммы
            if NGRAMS_RU and NGRAMS_EN:
                prob_ru = word_probability(ru_variant, 'ru')
                prob_en = word_probability(w, 'en')

                if prob_ru > prob_en + 5:
                    log(f"[Short-Stat] '{w}' → ru: prob_ru={prob_ru:.2f} > prob_en={prob_en:.2f}")
                    return "ru"

        if has_cyrillic and not has_latin:
            if en_variant in SHORT_EN or en_variant in EN_WORDS:
                log(f"[Short] '{w}' → en: '{en_variant}' найдено")
                return "en"

            # НОВОЕ: Проверяем через n-граммы
            if NGRAMS_RU and NGRAMS_EN:
                prob_ru = word_probability(w, 'ru')
                prob_en = word_probability(en_variant, 'en')

                if prob_en > prob_ru + 5:
                    log(f"[Short-Stat] '{w}' → en: prob_en={prob_en:.2f} > prob_ru={prob_ru:.2f}")
                    return "en"

        return None

    # Конвертируем и проверяем точное совпадение
    ru_variant = convert(w, "ru").replace("ё", "е")
    en_variant = convert(w, "en")

    # Точное совпадение в словаре (быстро)
    if has_latin and not has_cyrillic and ru_variant in RU_WORDS:
        return "ru"
    if has_cyrillic and not has_latin and en_variant in EN_WORDS:
        return "en"

    # Fuzzy matching для слов ≥4 символов
    if len(w) >= FUZZY_MIN_WORD_LENGTH:
        if has_latin and not has_cyrillic:
            closest_ru = find_closest_word_fast(ru_variant, "ru")
            if closest_ru:
                log(f"[Fuzzy] '{w}' → '{ru_variant}' ≈ '{closest_ru}' (ru)")
                return "ru"

        if has_cyrillic and not has_latin:
            closest_en = find_closest_word_fast(en_variant, "en")
            if closest_en:
                log(f"[Fuzzy] '{w}' → '{en_variant}' ≈ '{closest_en}' (en)")
                return "en"

    return None


# ---------------------------------------------------------------------------
# Состояние программы
# ---------------------------------------------------------------------------
kb_out = Controller()
state_lock = threading.Lock()
jobs = queue.Queue()
busy = threading.Event()
buffer = []
last_word = ""
last_sep = ""
auto_enabled = True
held_mods = set()

shift_down_time = 0.0
shift_clean = False
last_shift_tap = 0.0

MODS = {Key.cmd, Key.cmd_r, Key.ctrl, Key.ctrl_r, Key.alt, Key.alt_r, Key.shift, Key.shift_r}
SHIFT_KEYS = {Key.shift, Key.shift_r}
SHORTCUT_MODS = {Key.cmd, Key.cmd_r, Key.ctrl, Key.ctrl_r, Key.alt, Key.alt_r}


# ---------------------------------------------------------------------------
# Работа с текстом
# ---------------------------------------------------------------------------
def retype(n_delete, text):
    """Удаляет n_delete символов и печатает text."""
    busy.set()
    try:
        for _ in range(n_delete):
            kb_out.press(Key.backspace)
            kb_out.release(Key.backspace)
            time.sleep(0.02)
        time.sleep(0.05)
        kb_out.type(text)
        time.sleep(0.1)
    finally:
        time.sleep(0.3)
        busy.clear()


def job_auto_fix(word, sep, target):
    fixed = convert(word, target)
    log(f"Исправлено: '{word}' → '{fixed}' (раскладка → {target})")
    retype(len(word) + len(sep), fixed + sep)
    switch_layout(target)
    with state_lock:
        global last_word, last_sep
        last_word, last_sep = fixed, sep


def job_manual_fix():
    global buffer, last_word, last_sep
    with state_lock:
        if buffer:
            word, sep = "".join(buffer), ""
        elif last_word:
            word, sep = last_word, last_sep
        else:
            log("Ручное исправление: слов для исправления нет")
            return
        buffer = []
    target = "en" if current_layout() == "ru" else "ru"
    fixed = convert(word, target)
    log(f"Ручное исправление: '{word}' → '{fixed}' (раскладка → {target})")
    retype(len(word) + len(sep), fixed + sep)
    switch_layout(target)
    with state_lock:
        last_word, last_sep = fixed, sep


def toggle_auto():
    global auto_enabled
    auto_enabled = not auto_enabled
    log(f"Автоматический режим: {'ВКЛ' if auto_enabled else 'ВЫКЛ'}")


# ---------------------------------------------------------------------------
# Слушаем клавиатуру
# ---------------------------------------------------------------------------
def on_press(key):
    global buffer, last_word, last_sep, shift_down_time, shift_clean, last_shift_tap
    if busy.is_set():
        return

    if key in SHIFT_KEYS:
        held_mods.add(key)
        if not held_mods - SHIFT_KEYS - {Key.shift}:
            if not shift_down_time or time.time() - shift_down_time > 0.5:
                shift_down_time = time.time()
                shift_clean = True
        return
    if key in MODS:
        held_mods.add(key)
        return

    shift_clean = False

    with state_lock:
        if held_mods & SHORTCUT_MODS:
            buffer = []
            return

        if key in (Key.space, Key.enter, Key.tab):
            if buffer:
                word = "".join(buffer)
                buffer = []
                sep = " " if key == Key.space else ""
                last_word, last_sep = word, sep
                if auto_enabled and key == Key.space:
                    target = decide(word)
                    if target:
                        busy.set()
                        jobs.put(lambda w=word, s=sep, t=target: job_auto_fix(w, s, t))
            else:
                last_word, last_sep = "", ""
            return

        if key == Key.backspace:
            if buffer:
                buffer.pop()
            return

        char = getattr(key, "char", None)
        if char and len(char) == 1 and char.isprintable():
            buffer.append(char)
            return

        buffer = []


def on_release(key):
    global shift_clean, last_shift_tap, shift_down_time
    held_mods.discard(key)
    if key in SHIFT_KEYS and shift_clean and not (held_mods & SHIFT_KEYS):
        shift_clean = False
        now = time.time()
        if now - last_shift_tap <= DOUBLE_SHIFT_SEC:
            last_shift_tap = 0.0
            log("Двойной Shift: ручное исправление")
            jobs.put(job_manual_fix)
        else:
            last_shift_tap = now


# ---------------------------------------------------------------------------
# Главный поток
# ---------------------------------------------------------------------------
def main():
    log("=== Punto v5 с обработкой смешанных раскладок запущен ===")
    log("Двойной Shift или Control+Option+Z - исправить слово, Control+Option+P - вкл/выкл авто")
    hotkeys = keyboard.GlobalHotKeys({
        "<ctrl>+<alt>+z": lambda: jobs.put(job_manual_fix),
        "<ctrl>+<alt>+p": lambda: jobs.put(toggle_auto),
    })
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    hotkeys.start()
    listener.start()

    while True:
        try:
            job = jobs.get(timeout=1)
        except queue.Empty:
            continue
        try:
            job()
        except Exception:
            log("[!] Ошибка:\n" + traceback.format_exc())
        finally:
            busy.clear()


if __name__ == "__main__":
    main()
