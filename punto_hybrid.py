#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Punto Hybrid - полные словари + LLM для неизвестных слов
"""

import os
import queue
import sys
import threading
import time
import traceback
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

# Настройки LLM
LLM_ENABLED = True
LLM_API_URL = "http://localhost:11434/api/generate"
LLM_MODEL = "qwen2.5-coder:1.5b"
CACHE_SIZE = 50000  # Большой кэш для скорости

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
# Системные функции переключения раскладки
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
# Загрузка полных словарей
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
        return set()


# ПОЛНЫЕ словари для максимального покрытия
EN_WORDS = load_words(
    "words_en.txt",
    "the and you that have for not with this but from they we say hello thanks "
    "please yes hi ok world code good night morning",
)
RU_WORDS = load_words(
    "words_ru.txt",
    "и в не на что он я с как а то все она так его но да ты к у же вы за "
    "привет спасибо пожалуйста работа сегодня просто время",
)
EXCEPTIONS = load_exceptions("exceptions.txt")

SHORT_EN = {"am", "an", "as", "at", "be", "by", "do", "go", "he", "hi", "if", "in",
            "is", "it", "me", "my", "no", "of", "ok", "on", "or", "so", "to", "up", "us", "we"}
SHORT_RU = {"ам", "ах", "ба", "бы", "ва", "во", "да", "до", "ее", "ей", "ем", "ею",
            "её", "же", "за", "из", "им", "их", "ко", "ли", "мы", "на", "не", "ни",
            "но", "ну", "об", "ой", "он", "от", "по", "ра", "са", "се", "си", "со",
            "та", "те", "ти", "то", "ту", "ты", "уж", "ух", "эй", "эх", "юг", "юз", "як", "ям"}


# ---------------------------------------------------------------------------
# LLM для неизвестных слов
# ---------------------------------------------------------------------------
def ask_llm(word):
    """Спрашивает LLM только для неизвестных слов."""
    if not LLM_ENABLED or len(word) > 15:
        return None

    try:
        import requests

        prompt = f"""Is "{word}" typed in wrong keyboard layout?
Reply ONLY ONE WORD:
- "RU" if it should be Russian (typed in English layout)
- "EN" if it should be English (typed in Russian layout)
- "NO" if correct or unknown

Answer:"""

        response = requests.post(
            LLM_API_URL,
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 3
                }
            },
            timeout=0.3
        )

        if response.status_code == 200:
            result = response.json()
            answer = result.get("response", "").strip().upper()

            if "RU" in answer[:10]:
                return "ru"
            elif "EN" in answer[:10]:
                return "en"
    except Exception:
        pass

    return None


@lru_cache(maxsize=CACHE_SIZE)
def decide(word):
    """
    Определяет язык для исправления.
    Сначала словари, потом LLM для неизвестных.
    """
    if len(word) > 20:
        return None

    w = word.lower().replace("ё", "е")

    if w in EXCEPTIONS:
        return None

    has_cyrillic = any('Ѐ' <= c <= 'ӿ' for c in w)
    has_latin = any('a' <= c.lower() <= 'z' for c in w)

    # Быстрая проверка в словарях
    if has_cyrillic and w in RU_WORDS:
        return None
    if has_latin and w in EN_WORDS:
        return None

    # Короткие слова
    if len(w) <= 2:
        if w in SHORT_EN or w in SHORT_RU or w in EN_WORDS or w in RU_WORDS:
            return None
        if len(w) == 2:
            if convert(w, "en") in SHORT_EN:
                return "en"
            if convert(w, "ru") in SHORT_RU:
                return "ru"
        return None

    # Проверяем конвертацию
    if has_latin and not has_cyrillic:
        ru_variant = convert(w, "ru").replace("ё", "е")
        if ru_variant in RU_WORDS:
            return "ru"
        # Если не нашли в словаре - спросим LLM
        llm_result = ask_llm(word)
        if llm_result:
            log(f"[LLM] '{word}' -> {llm_result}")
            return llm_result

    if has_cyrillic and not has_latin:
        en_variant = convert(w, "en")
        if en_variant in EN_WORDS:
            return "en"
        # Если не нашли в словаре - спросим LLM
        llm_result = ask_llm(word)
        if llm_result:
            log(f"[LLM] '{word}' -> {llm_result}")
            return llm_result

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
            time.sleep(0.01)
        time.sleep(0.02)
        kb_out.type(text)
        time.sleep(0.05)
    finally:
        time.sleep(0.15)
        busy.clear()


def job_auto_fix(word, sep, target):
    fixed = convert(word, target)
    log(f"Исправлено: '{word}' -> '{fixed}' (раскладка -> {target})")
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
            log("Ручное исправление: нет слова для исправления")
            return
        buffer = []

    # Определяем целевой язык
    target = "en" if current_layout() == "ru" else "ru"
    fixed = convert(word, target)
    log(f"Ручное исправление: '{word}' -> '{fixed}' (раскладка -> {target})")
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
        if not held_mods - SHIFT_KEYS:
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
    global shift_clean, last_shift_tap
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
    log("=== Punto Hybrid (словари + LLM) запущен ===")
    log(f"LLM модель: {LLM_MODEL}")
    log("Двойной Shift или Ctrl+Opt+Z - исправить, Ctrl+Opt+P - вкл/выкл авто")

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
