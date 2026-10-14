#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Punto v4 - статистический анализ с n-граммами
Использует вероятностную модель вместо простого сравнения со словарем
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

# Пороги для принятия решения
PROBABILITY_THRESHOLD = -10.0  # Минимальная вероятность для распознавания
CONFIDENCE_DIFF = 5.0  # Минимальная разница для уверенности


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
# Загрузка N-грамм и статистики
# ---------------------------------------------------------------------------
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


# Загружаем n-граммы
NGRAMS_RU = load_ngrams('ru')
NGRAMS_EN = load_ngrams('en')


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


EXCEPTIONS = load_exceptions("exceptions.txt")

# Короткие слова из 2 букв
SHORT_EN = {"am", "an", "as", "at", "be", "by", "do", "go", "he", "hi", "if", "in",
            "is", "it", "me", "my", "no", "of", "ok", "on", "or", "so", "to", "up",
            "us", "we"}
SHORT_RU = {"ам", "ах", "ба", "бы", "ва", "во", "да", "до", "ее", "ей", "ем", "ею",
            "её", "же", "за", "из", "им", "их", "ко", "ли", "мы", "на", "не", "ни",
            "но", "ну", "об", "ой", "он", "от", "по", "ра", "са", "се", "си", "со",
            "та", "те", "ти", "то", "ту", "ты", "уж", "ух", "эй", "эх", "юг", "юз",
            "як", "ям"}


# ---------------------------------------------------------------------------
# Вероятностная оценка слова
# ---------------------------------------------------------------------------
@lru_cache(maxsize=5000)
def word_probability(word, lang):
    """
    Вычисляет log-вероятность того, что слово принадлежит языку
    Чем больше значение, тем вероятнее слово
    """
    if len(word) < 2:
        return -100  # Слишком короткое

    ngrams = NGRAMS_RU if lang == 'ru' else NGRAMS_EN
    if not ngrams:
        return -100  # Нет статистики

    score = 0.0

    # 1. Проверка начальной буквы
    initial = word[0]
    initial_prob = ngrams['initials'].get(initial, 0.0001)
    score += 10 * initial_prob  # Вес начальной буквы

    # 2. Проверка биграмм
    for i in range(len(word) - 1):
        bigram = word[i:i+2]
        bigram_prob = ngrams['bigrams'].get(bigram, 0.0)

        if bigram_prob == 0.0:
            # Невозможная биграмма!
            score -= 20  # Сильный штраф
        else:
            score += 100 * bigram_prob  # Нормализованная вероятность

    # 3. Проверка триграмм (дополнительный вес)
    for i in range(len(word) - 2):
        trigram = word[i:i+3]
        trigram_prob = ngrams['trigrams'].get(trigram, 0.0)

        if trigram_prob > 0.0:
            score += 50 * trigram_prob
        else:
            score -= 5  # Легкий штраф за отсутствие

    # 4. Бонус за длину (длинные слова более показательны)
    if len(word) >= 5:
        score += 2 * len(word)

    return score


def decide(word):
    """
    Возвращает язык, на который надо исправить слово, или None.
    Использует статистическую модель n-грамм.
    """
    w = word.lower().replace("ё", "е")
    if w in EXCEPTIONS:
        return None

    # Определяем язык по символам в слове
    has_cyrillic = any('Ѐ' <= c <= 'ӿ' for c in w)
    has_latin = any('a' <= c.lower() <= 'z' for c in w)

    # Для коротких слов (1-2 символа) используем строгую проверку
    if len(w) <= 2:
        if w in SHORT_EN or w in SHORT_RU:
            return None
        if len(w) == 2:
            if convert(w, "en") in SHORT_EN:
                return "en"
            if convert(w, "ru") in SHORT_RU:
                return "ru"
        return None

    # Конвертируем в оба языка
    ru_variant = convert(w, "ru").replace("ё", "е")
    en_variant = convert(w, "en")

    # Вычисляем вероятности
    if has_latin and not has_cyrillic:
        # Слово набрано латиницей
        prob_ru = word_probability(ru_variant, 'ru')
        prob_en = word_probability(w, 'en')

        # Логируем для отладки
        if prob_ru > prob_en + CONFIDENCE_DIFF:
            log(f"[Stat] '{w}' → ru: prob_ru={prob_ru:.2f} > prob_en={prob_en:.2f} (Δ={prob_ru-prob_en:.2f})")
            return "ru"

    elif has_cyrillic and not has_latin:
        # Слово набрано кириллицей
        prob_ru = word_probability(w, 'ru')
        prob_en = word_probability(en_variant, 'en')

        if prob_en > prob_ru + CONFIDENCE_DIFF:
            log(f"[Stat] '{w}' → en: prob_en={prob_en:.2f} > prob_ru={prob_ru:.2f} (Δ={prob_en-prob_ru:.2f})")
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
    log("=== Punto v4 со статистическим анализом n-грамм запущен ===")
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
