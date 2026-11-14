"""backend_control.py - one control adapter for the S-4 probe (control_probe.py) over a thin OS backend, so that what is
portable (the mapping of the five tests to backend calls, the refusal handling) is tested here with fake backends and only the
backend itself (UI Automation, macOS Accessibility) is OS code that no test here can reach.

backend interface (every call may raise; an exception means "refused"):
  text() -> str | None        the whole text; None: the control cannot be read
  set_text(s) -> bool         whole-value write (ValuePattern.SetValue, AXValue); False: refused
  selection() -> (a, b)       code-point offsets of the selection, a == b is the caret
  set_selection(a, b)         move the selection / caret
  replace_selection(s) -> bool   replace the CURRENT selection by s (macOS: write AXSelectedText); False: the backend has no such write
  read_only() -> bool         the control reports itself as read-only"""


class BackendControl:
    def __init__(self, backend):
        self.b = backend

    def readable(self):
        return self.b.text() is not None

    def read(self):
        t = self.b.text()
        if t is None:
            raise RuntimeError("not readable")
        return t

    def set_value(self, text):
        if self.b.read_only():
            return False
        return bool(self.b.set_text(text))

    def select(self, a, b):
        self.b.set_selection(a, b)

    def selection(self):
        return tuple(self.b.selection())

    def replace(self, a, b, text):
        if self.b.read_only():
            return False
        self.b.set_selection(a, b)
        # the caret is NOT restored here: result 3 measures what the control does alone
        return bool(self.b.replace_selection(text))
