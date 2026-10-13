#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Punto-подобный переключатель раскладки для macOS.

Горячие клавиши:
  * Двойной Shift (быстро нажать и отпустить Shift два раза) - исправить последнее слово
  * Control + Option + L - тоже исправить последнее слово
  * Control + Option + P - включить / выключить автоматический режим

Автоматика: при нажатии пробела слово, которого нет в словаре своего языка,
но его перевод в другой раскладке есть в словаре, заменяется, и раскладка переключается.

Файлы рядом со скриптом:
  words_en.txt, words_ru.txt - словари (по одному слову в строке)
  exceptions.txt             - слова, которые программа никогда не трогает
  punto.log                  - журнал исправлений
"""

import os
import queue
import sys
import threading
import time
import traceback
from datetime import datetime

# Скрываем иконку приложения из дока (должно быть до импорта других модулей)
try:
    from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)
except Exception:
    pass  # Игнорируем ошибки, если не получается скрыть

import objc
from Foundation import NSBundle
from pynput import keyboard
from pynput.keyboard import Key, Controller

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "punto.log")
DOUBLE_SHIFT_SEC = 0.4  # максимальный промежуток между двумя нажатиями Shift


def log(msg):
    """Пишем только в файл. В консоль выводим, только если запущено вручную."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    if sys.stdout.isatty():
        print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 1. Системные функции переключения раскладки (HIToolbox)
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
    """Переключает раскладку на 'en' или 'ru'. Вызывать только из главного потока."""
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
# 2. Соответствие клавиш EN <-> RU (по позиции клавиш на клавиатуре)
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
# 3. Словари и исключения
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

# Короткие слова из 2 букв для особой обработки
SHORT_EN = {"am", "an", "as", "at", "be", "by", "do", "go", "he", "hi", "if", "in",
            "is", "it", "me", "my", "no", "of", "ok", "on", "or", "so", "to", "up",
            "us", "we"}
SHORT_RU = {"ам", "ах", "ба", "бы", "ва", "во", "да", "до", "ее", "ей", "ем", "ею",
            "её", "же", "за", "из", "им", "их", "ко", "ли", "мы", "на", "не", "ни",
            "но", "ну", "об", "ой", "он", "от", "по", "ра", "са", "се", "си", "со",
            "та", "те", "ти", "то", "ту", "ты", "уж", "ух", "эй", "эх", "юг", "юз",
            "як", "ям"}


def decide(word):
    """
    Возвращает язык, на который надо исправить слово, или None.
    Смотрим только на буквы слова, а не на текущую раскладку.
    """
    w = word.lower().replace("ё", "е")
    if w in EXCEPTIONS:
        return None

    # Определяем язык по символам в слове
    has_cyrillic = any('Ѐ' <= c <= 'ӿ' for c in w)
    has_latin = any('a' <= c.lower() <= 'z' for c in w)

    # Если слово уже в правильном языке, не трогаем
    if has_cyrillic and w in RU_WORDS:
        return None
    if has_latin and w in EN_WORDS:
        return None

    # Для коротких слов (1-2 символа) более строгая проверка
    if len(w) <= 2:
        if w in SHORT_EN or w in SHORT_RU or w in EN_WORDS or w in RU_WORDS:
            return None
        if len(w) == 2:
            if convert(w, "en") in SHORT_EN:
                return "en"
            if convert(w, "ru") in SHORT_RU:
                return "ru"
        return None

    # Проверяем, есть ли конвертация этого слова в словаре
    ru_variant = convert(w, "ru").replace("ё", "е")
    en_variant = convert(w, "en")

    # Если слово латинское, но его русская версия есть в словаре
    if has_latin and not has_cyrillic and ru_variant in RU_WORDS:
        return "ru"

    # Если слово кириллическое, но его английская версия есть в словаре
    if has_cyrillic and not has_latin and en_variant in EN_WORDS:
        return "en"

    return None


# ---------------------------------------------------------------------------
# 4. Состояние программы
# ---------------------------------------------------------------------------
kb_out = Controller()
state_lock = threading.Lock()
jobs = queue.Queue()          # задачи для главного потока
busy = threading.Event()      # True, пока программа сама печатает
buffer = []                   # символы текущего слова
last_word = ""                # последнее законченное слово
last_sep = ""                 # что стояло после него
auto_enabled = True
held_mods = set()

# Для двойного Shift
shift_down_time = 0.0         # когда нажали Shift
shift_clean = False           # Shift нажат и с ним ещё не нажималась другая клавиша
last_shift_tap = 0.0          # время последнего «чистого» отпускания Shift

MODS = {Key.cmd, Key.cmd_r, Key.ctrl, Key.ctrl_r, Key.alt, Key.alt_r, Key.shift, Key.shift_r}
SHIFT_KEYS = {Key.shift, Key.shift_r}
SHORTCUT_MODS = {Key.cmd, Key.cmd_r, Key.ctrl, Key.ctrl_r, Key.alt, Key.alt_r}


# ---------------------------------------------------------------------------
# 5. Работа с текстом (выполняется в главном потоке)
# ---------------------------------------------------------------------------
def retype(n_delete, text):
    """Удаляет n_delete символов и печатает text. busy блокирует перехват своих нажатий."""
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
            log("Ручное исправление: слов для исправления нет")
            return
        buffer = []
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
# 6. Слушаем клавиатуру (фоновый поток)
# ---------------------------------------------------------------------------
def on_press(key):
    global buffer, last_word, last_sep, shift_down_time, shift_clean, last_shift_tap
    if busy.is_set():
        return

    # Отслеживаем Shift для двойного нажатия
    if key in SHIFT_KEYS:
        held_mods.add(key)
        if not held_mods - SHIFT_KEYS - {Key.shift}:  # только Shift держится
            if not shift_down_time or time.time() - shift_down_time > 0.5:
                shift_down_time = time.time()
                shift_clean = True
        return
    if key in MODS:
        held_mods.add(key)
        return

    # Любая другая клавиша сбрасывает «чистое» нажатие Shift
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
                        busy.set()  # блокируем ввод до конца исправления
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
# 7. Главный поток: выполняет задачи, где можно трогать раскладку
# ---------------------------------------------------------------------------
def main():
    log("=== Punto запущен ===")
    log("Двойной Shift или Control+Option+L - исправить слово, Control+Option+P - вкл/выкл авто")
    hotkeys = keyboard.GlobalHotKeys({
        "<ctrl>+<alt>+l": lambda: jobs.put(job_manual_fix),
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
