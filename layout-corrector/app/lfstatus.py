"""AP-2 status: the icon always shows one of Active, Paused, Manual only, Off. The label is derived from the runtime, never stored.
Readings of mine (listed in audit/AP7_RT19_readings.md, section 8): a missing permission or a missing instance lock shows Off even while paused, so that the
icon can name the missing permission (AP-1); otherwise paused wins over the mode; with no focused application the state is Off with the reason 'no_focus'."""
LABELS = ("Active", "Paused", "Manual only", "Off")
GLOBAL_OFF = ("permission", "instance")          # reasons that make the whole tool Off, whatever the application


def status(rt):
    """(label, reasons): reasons are the short codes of Runtime.explain, plus 'paused' or 'no_focus'; the icon names the first one."""
    if rt.ad is None or rt.app_id is None:
        return "Off", ["no_focus"]
    mode, reasons = rt.explain(rt.app_id)
    g = [r for r in reasons if r in GLOBAL_OFF]
    if g:
        return "Off", g
    if rt.paused:
        return "Paused", ["paused"]
    if mode == "OFF":
        return "Off", reasons
    if mode == "MANUAL_ONLY":
        return "Manual only", reasons
    return "Active", reasons
