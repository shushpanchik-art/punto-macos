"""Fuzz of run_transaction against an INDEPENDENT oracle (cell identity, not strings).
The field is a list of cells (id, char, origin).  Origins: 'O' original, 'U' typed by the user during the transaction,
'W' written by the tool.  Random environment operations (user key, silent key, arrow, mouse click, Backspace, Delete,
edits outside the fragment) and random adapter faults are injected before ANY adapter call.
Oracle (G-FIELD of 13.2):
  VERIFIED  -> every original cell outside the fragment is still there in order, every user cell that the user did
               not delete is still there, the n word cells have been replaced by exactly the cells of `new`, the
               Space and typed-ahead cells are the original cells, and the tool changed nothing else.
  RESTORED / ABORTED -> the text of the fragment cells equals what the user typed (the tool left no trace).
  ABORTED   -> the tool wrote nothing.
Every deviation is a "violation"; they are grouped by a signature and the first seed of each group is printed.
Usage: python3 attack_fuzz_transaction.py [runs=60000] [seed=1]
Environment faults the specification itself excludes from G-FIELD (an application that changes text OUTSIDE the
fragment, 'neighbour') are counted separately, see attack_neighbour_damage.py."""
import sys, os, random, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

M1 = frozenset({L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK})
M2 = frozenset({L.READ_RANGE, L.SYNTHETIC_INPUT})
OLD, NEW = "ghbdtn", "привет"


class CellField(L.Adapter):
    def __init__(self, rng, caps, prefix, ahead, env_p, fault_p, click_ok=True, neighbour=False):
        self.rng, self.caps, self.env_p, self.fault_p = rng, frozenset(caps), env_p, fault_p
        self.click_ok, self.neighbour = click_ok, neighbour
        self.cells, self.nid = [], 0
        for ch in prefix + OLD + " " + ahead:
            self.cells.append((self._id(), ch, "O"))
        self.pos = len(self.cells)
        self.frag_ids = [c[0] for c in self.cells[len(prefix):]]       # word, Space, typed-ahead
        self.word_ids = self.frag_ids[:len(OLD)]
        self.keys = 0                      # counted user key events
        self.user_deleted = set()
        self.tool_wrote = False
        self.touched = False               # the user changed something inside the fragment
        self.outside_damage = False
        self.n_calls = 0
        self.snap = None

    def _id(self):
        self.nid += 1
        return self.nid

    # --- helpers
    def text(self, a=None, b=None):
        return "".join(c[1] for c in self.cells[a:b])

    def _env(self):
        r = self.rng
        if r.random() >= self.env_p:
            return
        op = r.choice(("type", "type", "silent", "arrow", "click", "bs", "del", "outside"))
        if op == "type":
            self._user_insert(r.choice("xyz,"))
            self.keys += 1
        elif op == "silent":
            self.keys += 1
        elif op == "arrow":
            self.pos = max(0, min(len(self.cells), self.pos + r.choice((-3, -2, -1, 1, 2))))
            self.keys += 1
        elif op == "click" and self.click_ok:
            self.pos = r.randrange(len(self.cells) + 1)
        elif op == "bs" and self.pos > 0:
            self._user_delete(self.pos - 1)
            self.pos -= 1
            self.keys += 1
        elif op == "del" and self.pos < len(self.cells):
            self._user_delete(self.pos)
            self.keys += 1
        elif op == "outside" and self.neighbour and self.cells:
            i = r.randrange(len(self.cells))
            if self.cells[i][0] not in self.frag_ids:
                self.cells[i] = (self.cells[i][0], "#", "O")
                self.outside_damage = True

    def _user_insert(self, ch):
        i = self.pos
        if 0 < i < len(self.cells) and self.cells[i - 1][0] in self.frag_ids and self.cells[i][0] in self.frag_ids:
            self.touched = True
        self.cells.insert(i, (self._id(), ch, "U"))
        self.pos += 1

    def _user_delete(self, i):
        cid = self.cells[i][0]
        if cid in self.frag_ids:
            self.touched = True
        self.user_deleted.add(cid)
        del self.cells[i]

    def _fault(self, names):
        return self.rng.choice(names) if self.rng.random() < self.fault_p else None

    # --- adapter
    def gate(self):
        self._env()
        f = self._fault(("DENY", "UNKNOWN", "raise"))
        if f == "raise":
            raise L.AdapterError("gate")
        return f or L.GATE_ALLOW

    def caret(self):
        self._env()
        f = self._fault(("back", "forward", "raise"))
        if f == "raise":
            raise L.AdapterError("caret")
        return self.pos + {"back": -1, "forward": 1}.get(f, 0)

    def read(self, s, e):
        self._env()
        f = self._fault(("none", "stale", "raise"))
        if f == "raise":
            raise L.AdapterError("read")
        if f == "none":
            return None
        t = self.text(s, e)
        self.snap = (list(self.cells), self.touched, self.outside_damage, set(self.user_deleted))   # state at the last read
        return t[:-1] + "?" if f == "stale" and t else t

    def replace(self, s, e, text):
        self._env()
        f = self._fault(("raise", "partial", "applied_error", "autocorrect", "ignored", "spill"))
        if f == "raise":
            raise L.AdapterError("replace")
        if f == "ignored":
            return
        w = text[:len(text) // 2] + self.text(s + len(text) // 2, e) if f == "partial" else text
        if f == "partial":                                                  # keep cell identity of the untouched half
            keep = self.cells[s + len(text) // 2:e]
            new = [(self._id(), ch, "W") for ch in text[:len(text) // 2]] + keep
        else:
            if f == "autocorrect":
                text = text[:-1] + "?"
            new = [(self._id(), ch, "W") for ch in text]
        self.tool_wrote = True
        tail = self.cells[e:]
        if f == "spill" and tail:
            tail = [(tail[0][0], "?", tail[0][2])] + tail[1:]
        self.cells = self.cells[:s] + new + tail
        if f in ("partial", "applied_error"):
            raise L.AdapterError("replace")

    def send(self, events):
        for k, (kind, ch) in enumerate(events, 1):
            self._env()
            f = self._fault(("raise", "drop"))
            if f == "raise":
                raise L.AdapterError("send")
            if f == "drop":
                continue
            self.tool_wrote = True
            if kind == "bs":
                if self.pos > 0:
                    del self.cells[self.pos - 1]
                    self.pos -= 1
            else:
                self.cells.insert(self.pos, (self._id(), ch, "W"))
                self.pos += 1

    def modifier_down(self):
        return False

    def mark(self):
        self._env()
        return self.keys

    def keys_since(self, m):
        self._env()
        return self.keys - m


def oracle(f, r, prefix, ahead, a_used, m2):
    """None when fine, else a violation signature (see the module docstring)."""
    n = len(OLD)
    if r.outcome == "ABORTED" and f.tool_wrote:
        return "ABORTED but the tool wrote"
    if r.outcome == "VERIFIED":
        cells, touched, outside, udel = f.snap                    # the field when the verifying read returned
        if outside:
            return "NEIGHBOUR"
        ids = [c[0] for c in cells]
        pre_ids = [i for i in range(1, len(prefix) + 1)]
        sp_id = f.frag_ids[n]
        ahead_ids = f.frag_ids[n + 1:]
        # drop the user's cells: a key typed by the user after the fragment is not the tool's business
        seq = [c for c in cells if c[2] != "U"]
        w = [c for c in seq if c[2] == "W"]
        want = NEW + (" " if m2 else "")
        if "".join(c[1] for c in w) != want:
            return "VERIFIED but the tool-written text is %r" % "".join(c[1] for c in w)
        if any(cid in ids for cid in f.word_ids):
            return "VERIFIED but old word cells are still in the field (stray characters of the old word)"
        i0 = seq.index(w[0])
        left = [c[0] for c in seq[:i0]]
        if left != [i for i in pre_ids if i not in udel]:
            return "VERIFIED, wrong word converted or text before the word changed"
        right = [c[0] for c in seq[i0 + len(w):]]
        want_right = ([] if m2 else [sp_id]) + [i for i in ahead_ids if i not in udel]
        if right != want_right:
            return "VERIFIED but the text after the new word is not Space + typed-ahead: %r" % "".join(c[1] for c in seq[i0 + len(w):])
        # user cells inside the fragment (between the written cells) are a corruption as well
        pos = [ids.index(c[0]) for c in w]
        if pos != list(range(pos[0], pos[0] + len(w))):
            return "VERIFIED but a user key landed inside the new word"
        return None
    return None


def one(seed, caps, mode):
    rng = random.Random(seed)
    prefix = rng.choice(("", "Hello ", "ghbdtn ", "ghbdtn ghbdtn ", "a ", "x" * rng.randrange(0, 10) + " "))
    ahead = rng.choice(("", "", "", "a", "ab", "abc", "abcd"))
    f = CellField(rng, caps, prefix, ahead, env_p=rng.choice((0.0, 0.05, 0.15)), fault_p=rng.choice((0.0, 0.03, 0.1)),
                  neighbour=False)
    r = L.run_transaction(f, OLD, NEW, ahead, mode=mode)
    return f, r, prefix, ahead


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
    base = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    stats = collections.Counter()
    viol = collections.OrderedDict()
    for i in range(runs):
        caps, mode = ((M1, "AUTO"), (M2, "MANUAL_ONLY"), (M1 | {L.SYNTHETIC_INPUT}, "MANUAL_ONLY"))[i % 3]
        seed = base * 10_000_000 + i
        try:
            f, r, prefix, ahead = one(seed, caps, mode)
        except Exception as e:
            stats["EXC " + type(e).__name__] += 1
            viol.setdefault("exception " + type(e).__name__, seed)
            continue
        stats[r.outcome] += 1
        v = oracle(f, r, prefix, ahead, len(ahead), L.REPLACE_RANGE not in caps)
        if v:
            stats["violation"] += 1
            viol.setdefault(f"{'M1' if L.REPLACE_RANGE in caps else 'M2'} {r.outcome} {r.reason}: {v}", (seed, prefix, ahead, f.text()))
    print("runs", runs, dict(stats))
    for k, v in viol.items():
        print("  VIOLATION:", k, "| first seed/prefix/ahead/field:", v)
