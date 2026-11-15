"""AP-3 layout pair, deterministic part: from the installed input sources (each given by the 94 entries that the OS adapter read for it) choose the pair of one
English and one Russian layout, or say that the user must choose, or that there is no supported pair; and tell the runtime whether the ACTIVE source is usable.
No operating-system call here: the entries come from the adapter (13.7, RT-15), nothing is inferred from a name or a language id.

Specification: AP-3 "Detected from the installed input sources, where supported means that the fingerprint equals the table (13.7): when exactly one supported
English layout and one supported Russian layout are installed, that pair is used; otherwise the user chooses; an unsupported variant switches the tool off for it
with the notice of failure row 7"; 13.5 row 7 "OFF for that layout, and for the pair until a supported layout is active again; the status icon says layout not supported".
NOT defined by the text, so open (audit/AP7_RT19_readings.md, section 11): where the user's choice is kept (the settings schema has no field for it: here memory
only), what 'otherwise the user chooses' means when no supported layout of one language is installed (here: no pair, OFF), how two installed sources with the same
fingerprint are treated (here: both are supported, so the user chooses)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402

PAIR, CHOOSE, NONE = "PAIR", "CHOOSE", "NONE"
MAX_SOURCES = 64
_ID = re.compile(r"[^\x00-\x1f\x7f]{1,256}")


class Source:
    """An installed input source. `entries` is the list of 94 entries read by the adapter, or None when the source is not a keyboard layout or cannot be read."""
    __slots__ = ("id", "entries")

    def __init__(self, source_id, entries):
        self.id, self.entries = source_id, entries

    def __repr__(self):                      # entries are key tables, never text typed by the user, but they stay out of logs anyway
        return f"Source({self.id!r})"


def classify(source):
    """'en', 'ru' or None. None for anything that is not exactly a supported table: a changed table, a dead-key table, a source that cannot be read, a wrong shape."""
    e = source.entries
    if e is None or not isinstance(e, (list, tuple)):
        return None
    try:
        return L.identify_layout(e)
    except ValueError:
        return None
    except Exception:
        return None


class PairResult:
    """state PAIR (`en`, `ru` are source ids), CHOOSE (several supported sources: `candidates` per language) or NONE (no supported English or Russian source)."""
    def __init__(self, state, en=None, ru=None, candidates=None, unsupported=(), origin=""):
        self.state, self.en, self.ru = state, en, ru
        self.candidates = candidates or {"en": [], "ru": []}
        self.unsupported = list(unsupported)
        self.origin = origin                 # "single" (the only candidates) or "user"

    def layout_of(self, source_id):
        """'en' or 'ru' when the source is part of the chosen pair, else None."""
        if self.state != PAIR:
            return None
        return "en" if source_id == self.en else ("ru" if source_id == self.ru else None)


def select_pair(sources, chosen=None):
    """`sources`: list of Source. `chosen`: {'en': id, 'ru': id} from the user, used only when both ids are among the supported candidates. Returns a PairResult.
    A malformed list (too long, bad or repeated ids) is NONE: nothing is guessed."""
    if not isinstance(sources, (list, tuple)) or len(sources) > MAX_SOURCES:
        return PairResult(NONE)
    ids = []
    for s in sources:
        if not isinstance(s, Source) or not isinstance(s.id, str) or not _ID.fullmatch(s.id) or s.id in ids:
            return PairResult(NONE)
        ids.append(s.id)
    cand, unsupported = {"en": [], "ru": []}, []
    for s in sources:
        lay = classify(s)
        (cand[lay] if lay else unsupported).append(s.id)
    if not cand["en"] or not cand["ru"]:
        return PairResult(NONE, candidates=cand, unsupported=unsupported)
    if len(cand["en"]) == 1 and len(cand["ru"]) == 1:
        return PairResult(PAIR, cand["en"][0], cand["ru"][0], cand, unsupported, "single")
    if isinstance(chosen, dict) and set(chosen) == {"en", "ru"} and chosen["en"] in cand["en"] and chosen["ru"] in cand["ru"]:
        return PairResult(PAIR, chosen["en"], chosen["ru"], cand, unsupported, "user")
    return PairResult(CHOOSE, candidates=cand, unsupported=unsupported)


def apply_active(runtime, pair, active_source_id):
    """Row 7: the tool is OFF while the active source is not a member of the chosen pair (an unsupported variant, a source that is not a layout, a pair that is not
    chosen yet), and works again when a member is active. Returns the layout 'en' or 'ru' of the active source, or None. Sets `runtime.layout_ok` only."""
    lay = pair.layout_of(active_source_id) if isinstance(pair, PairResult) else None
    runtime.layout_ok = lay is not None
    runtime.apply_mode()
    return lay
