"""AP-1 first run and permissions, portable part, with a fake permission adapter. No operating system is asked anything; no real prompt, no real settings pane."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lffirstrun as F, lfruntime as R, lfengine as L, lfstatus as ST, lfnotify as N, lfpair as P

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

class Fake:
    """status: name -> 'granted'/'denied'/other; answers: name -> what request() returns (and, for 'granted', the status becomes granted)."""
    def __init__(self, st=None, answers=None):
        self.st = {"input_monitoring": "denied", "post_event": "denied", "accessibility": "denied"}
        self.st.update(st or {}); self.answers = dict(answers or {}); self.calls = []; self.fail_status = False; self.fail_request = False; self.links = {}
    def status(self, n):
        if self.fail_status: raise RuntimeError("os")
        return self.st[n]
    def request(self, n):
        self.calls.append(n)
        if self.fail_request: raise RuntimeError("os")
        a = self.answers.get(n, "pending")
        if a == "granted": self.st[n] = "granted"
        return a
    def settings_link(self, n):
        return self.links.get(n, "pane." + n)

ORDER = list(F.MACOS_ORDER)
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
def new():
    rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=False))
    f = L.SimField("", M1); rt.on_focus("A", f, "AUTO"); rt.on_gate(L.GATE_ALLOW); return rt, f
def typed(rt, f, w, t0):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        f.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", t0 + i), sig=("k", t0 + i))
def space(rt, f, t): f.type_user(" "); return rt.on_hook_event(L.Event("space", None, "en", t))
def rt_ready(): return new()[0]

# ---- construction
for bad in ("x", ("hook",), ("zz",), ("input_monitoring", "input_monitoring"), None, 5, tuple(["input_monitoring"] * 9)):
    try: F.FirstRun(Fake(), bad); T(False, f"rejected {bad!r}")
    except ValueError: T(True, "")
T(F.FirstRun(Fake(), ()).all_granted() and F.FirstRun(Fake(), ()).view()["screen"] == F.DONE, "no permission to request (Windows): done at once")
T(F.MACOS_ORDER == ("input_monitoring", "post_event", "accessibility"), "the order of 13.7")

# ---- the first run: the information screen, then one permission at a time
a = Fake(); fr = F.FirstRun(a)
v = fr.view()
T(v["screen"] == F.INTRO and v["state"] == "OFF" and v["can_quit"] and v["permission"] == "input_monitoring" and v["missing"] == ORDER, "the first screen is the information screen, state OFF, quit possible")
T(v["observed"] == list(F.OBSERVED) and len(v["observed"]) == 4 and all(x.startswith("firstrun.observed.") for x in v["observed"]), "what is observed is named by identifiers")
T(a.calls == [], "showing the screen asks the OS for nothing")
fr.acknowledge(); v = fr.view()
T(v["screen"] == F.PERMISSION and v["permission"] == "input_monitoring" and v["link"] == "pane.input_monitoring" and not v["prompt_open"] and a.calls == [], "one permission, with its link, no request yet")
T(fr.request_current() == "input_monitoring" and a.calls == ["input_monitoring"] and fr.view()["prompt_open"], "the press asks for the current one only")
T(fr.request_current() is None and a.calls == ["input_monitoring"] and fr.counters["duplicate_press"] == 1, "a repeated press while the prompt is open does nothing")
a.st["input_monitoring"] = "granted"                              # the user grants it in the OS
v = fr.view()
T(v["permission"] == "post_event" and v["missing"] == ["post_event", "accessibility"] and not v["prompt_open"] and a.calls == ["input_monitoring"], "granted: the next one, nothing is requested on its own")
T(fr.refresh() is False and fr.refresh() is False and a.calls == ["input_monitoring"], "repeated refresh with the same facts changes nothing")
T(fr.request_current() == "post_event" and a.calls == ["input_monitoring", "post_event"], "the second is asked only after the first")
a.st["post_event"] = "granted"; a.st["accessibility"] = "granted"
v = fr.view()
T(v["screen"] == F.DONE and v["state"] == "READY" and v["missing"] == [] and fr.all_granted(), "all granted: done")
T(fr.request_current() is None and fr.counters["nothing_to_ask"] == 1 and len(a.calls) == 2, "nothing more to ask")

# ---- the order of asking never skips ahead
a = Fake(); fr = F.FirstRun(a); fr.acknowledge()
for _ in range(3): fr.request_current()
T(a.calls == ["input_monitoring"], "the later permissions are not requested while the first is missing")

# ---- already granted
a = Fake({"input_monitoring": "granted", "accessibility": "granted"}); fr = F.FirstRun(a); fr.acknowledge()
T(fr.view()["permission"] == "post_event" and fr.missing() == ["post_event"], "already granted permissions are skipped")
fr.request_current(); T(a.calls == ["post_event"], "only the missing one is asked")
a = Fake({k: "granted" for k in ORDER}); fr = F.FirstRun(a)
T(fr.view()["screen"] == F.DONE and a.calls == [], "all granted before the first screen: no request, not even the screen's permission step")

# ---- denial
a = Fake(answers={"input_monitoring": "denied"}); fr = F.FirstRun(a); fr.acknowledge()
fr.request_current(); v = fr.view()
T(v["denied"] and v["state"] == "OFF" and v["permission"] == "input_monitoring" and v["link"] == "pane.input_monitoring" and not v["prompt_open"] and a.calls == ["input_monitoring"], "denied: OFF, the same permission, the link to the pane stays")
T(a.calls == ["input_monitoring"] and fr.current() == "input_monitoring", "denial asks for nothing by itself")
fr.request_current(); T(a.calls == ["input_monitoring"] * 2, "a new press after the answer is a new user action")
a.st["input_monitoring"] = "granted"; v = fr.view()
T(not v["denied"] and v["permission"] == "post_event", "granted later in the pane: the denial is forgotten")

# ---- cancel
a = Fake(); fr = F.FirstRun(a); fr.acknowledge(); fr.request_current()
fr.cancel(); v = fr.view()
T(not v["prompt_open"] and v["state"] == "OFF" and v["permission"] == "input_monitoring" and not fr.all_granted(), "cancel: OFF, no grant, no prompt open")
fr.cancel(); T(fr.counters["nothing_to_cancel"] == 1, "cancel with nothing open is counted and harmless")
T(len(a.calls) == 1, "cancel asks nothing")
fr.request_current(); T(len(a.calls) == 2, "after a cancel the user can ask again")

# ---- quit
quits = []
a = Fake(); fr = F.FirstRun(a, on_quit=lambda: quits.append(1))
T(fr.view()["can_quit"], "quit is possible on the first screen")
fr.quit(); fr.quit(); T(quits == [1] and fr.view()["screen"] == F.QUIT and fr.view()["state"] == "OFF", "quit calls the host once, state OFF")
fr.acknowledge(); T(fr.request_current() is None and a.calls == [] and fr.counters["ignored_after_quit"] == 1, "no request after quit")
fr.resume(); fr.acknowledge(); fr.request_current(); T(a.calls == ["input_monitoring"], "re-entry after a quit that did not end the process")
fr.quit(); T(quits == [1, 1], "the next quit calls the host again")
fr2 = F.FirstRun(Fake(), on_quit=lambda: 1 / 0); fr2.quit(); T(fr2.counters["quit_callback_failed"] == 1 and fr2.view()["screen"] == F.QUIT, "a failing host callback cannot break quitting")

# ---- re-entry: a new instance (restart) reads the facts again
a = Fake({"input_monitoring": "granted"}); fr = F.FirstRun(a)
T(fr.view()["screen"] == F.INTRO and fr.missing() == ["post_event", "accessibility"], "a restart shows the first screen again (the seen flag is memory only; open) and skips what is granted")

# ---- fail-safe: a failing or strange adapter never grants
for st in ("granted ", "GRANTED", True, 1, None, "ok", ""):
    fr = F.FirstRun(Fake({"input_monitoring": st}))
    T("input_monitoring" in fr.missing(), f"status {st!r} is not a grant")
a = Fake({k: "granted" for k in ORDER}); fr = F.FirstRun(a); a.fail_status = True
T(fr.refresh() is True and fr.missing() == ORDER and fr.counters["status_failed"] >= 3, "a failing status query: not granted")
a = Fake(); fr = F.FirstRun(a); fr.acknowledge(); a.fail_request = True
T(fr.request_current() == "input_monitoring" and fr.counters["request_failed"] == 1 and fr.view()["prompt_open"], "a failing request is treated as a prompt that has no answer yet")
a = Fake(answers={"input_monitoring": "granted"}); a.answers["input_monitoring"] = "granted"
fr = F.FirstRun(a); fr.acknowledge(); fr.request_current(); T(fr.current() == "post_event", "an answer 'granted' that the status confirms counts")
class Liar(Fake):
    def request(self, n): self.calls.append(n); return "granted"          # says granted, status still denied
a = Liar(); fr = F.FirstRun(a); fr.acknowledge(); fr.request_current()
T(fr.missing() == ORDER and fr.view()["prompt_open"], "an answer 'granted' that the status does not confirm is not believed")
for bad in (None, "", "a b", "x" * 200, 5, "../x\n"):
    a = Fake(); a.links["input_monitoring"] = bad; fr = F.FirstRun(a); fr.acknowledge()
    T(fr.view()["link"] is None, f"a bad link is dropped: {bad!r}")
class NoLink(Fake):
    def settings_link(self, n): raise RuntimeError("x")
fr = F.FirstRun(NoLink()); fr.acknowledge(); T(fr.view()["link"] is None, "a failing link query gives no link")

# ---- the runtime: OFF until every permission is granted, and the icon names the missing one
def rt_ready():
    """a runtime with a focused AUTO application, the way test_pair builds one"""
    rt = rt_new(); rt.apps["app"] = R.AppState("AUTO")
    ad = type("A", (), {"caps": frozenset(L.AUTO_REQUIRES) | {L.REPLACE_RANGE}})()
    rt.ad = ad; rt.app_id = "app"; rt.apps["app"].caps = ad.caps
    return rt
a = Fake(); fr = F.FirstRun(a); rt, f0 = new(); rt.permission_ok = True
T(fr.apply(rt) == "input_monitoring" and rt.permission_ok is False and rt.engine.mode == "OFF", "missing permission: the runtime is OFF")
T(fr.icon(rt) == ("Off", ["permission"], "input_monitoring"), "the icon names the missing permission")
a.st["input_monitoring"] = "granted"
T(fr.icon(rt) == ("Off", ["permission"], "post_event") and rt.engine.mode == "OFF", "still OFF while another permission is missing; the icon names that one")
a.st["post_event"] = "granted"; a.st["accessibility"] = "granted"
lab = fr.icon(rt)
T(lab[2] is None and rt.permission_ok and rt.engine.mode == "AUTO" and lab[0] == "Active", "all granted: the other facts decide (AUTO here)")
n_before = len(a.calls)
for _ in range(3): fr.apply(rt)
T(rt.engine.mode == "AUTO" and len(a.calls) == n_before, "repeated events: no change and no request")
# ---- revoke while running
a.st["accessibility"] = "denied"
lab = fr.icon(rt)
T(lab == ("Off", ["permission"], "accessibility") and rt.engine.mode == "OFF" and fr.revoked == ["accessibility"], "revoked while running: OFF at once, named, remembered")
T(fr.icon(rt)[2] == "accessibility" and fr.revoked == ["accessibility"], "the same revoke seen again is not recorded twice")
nt = N.Notifier(lambda n: True, lambda: 1000)
T(fr.notify(nt) == ["queued"] and fr.revoked == [], "a revoke is queued once")
nn = nt.pending[0][1]
T(nn["kind"] == "permission_missing" and nn["row"] == 14 and nn["action"] == "open_settings" and nn["params"] == {"permission": "accessibility"} and nn["takes_focus"] is False, "the notice names the permission, one action, no focus")
T(fr.notify(nt) == [] and len(nt.pending) == 1, "no second notice without a new loss")
a.st["accessibility"] = "granted"; fr.icon(rt); a.st["accessibility"] = "denied"; fr.icon(rt)
T(fr.revoked == ["accessibility"] and fr.notify(nt) == ["duplicate"], "a new loss while the first notice is still queued is a duplicate")
nt.deliver(); a.st["accessibility"] = "granted"; fr.icon(rt); a.st["accessibility"] = "denied"; fr.icon(rt)
T(fr.notify(nt) == ["suppressed"], "within 24 h of the shown notice: suppressed (13.5)")
a.st["accessibility"] = "granted"; lab = fr.icon(rt)
T(lab[0] == "Active" and rt.engine.mode == "AUTO", "granted again: back to what the facts allow")
# the first run itself queues nothing
a = Fake(); fr = F.FirstRun(a); fr.acknowledge(); fr.request_current(); fr.refresh()
nt = N.Notifier(lambda n: True, lambda: 0)
T(fr.notify(nt) == [] and nt.pending == [], "during the first run no notice is queued")
# a revoke of a permission that was never granted is not a revoke
a = Fake({"input_monitoring": "granted"}); fr = F.FirstRun(a); a.st["post_event"] = "denied"; fr.refresh(); T(fr.revoked == [], "never granted: not a revoke")
# losing the first of several while the rest stay granted
a = Fake({k: "granted" for k in ORDER}); fr = F.FirstRun(a); fr.refresh(); a.st["input_monitoring"] = "denied"; a.st["accessibility"] = "denied"
fr.refresh(); T(fr.revoked == ["input_monitoring", "accessibility"] and fr.current() == "input_monitoring", "two losses: both named, the first in order is asked first")
nt = N.Notifier(lambda n: True, lambda: 0); T(fr.notify(nt) == ["queued", "duplicate"], "both are submitted; one cause per 24 h shows once")

# ---- the pause and the pair: permission names first; the layout reason shows once the permission is there
a = Fake(); fr = F.FirstRun(a); rt, f0 = new(); rt.paused = True
T(fr.icon(rt) == ("Off", ["permission"], "input_monitoring"), "paused or not, the missing permission is named (AP-2 reading, section 8)")
EN, RU = L.table_entries("en"), L.table_entries("ru")
pr = P.select_pair([P.Source("us", EN)])
P.apply_active(rt, pr, "us")
T(rt.layout_ok is False and fr.icon(rt) == ("Off", ["permission"], "input_monitoring"), "no pair and no permission: the permission is named first")
for k in ORDER: a.st[k] = "granted"
lab = fr.icon(rt)
T(lab == ("Paused", ["paused"], None) and rt.permission_ok, "permission granted while paused: Paused (AP-2 precedence)")
rt.paused = False
lab = fr.icon(rt)
T(lab == ("Off", ["layout"], None) and rt.permission_ok, "permission granted: the layout reason shows")
pr = P.select_pair([P.Source("us", EN), P.Source("ru", RU)]); P.apply_active(rt, pr, "us")
T(fr.icon(rt) == ("Active", [], None), "both present: Active")
rt.layout_ok = True
a.st["input_monitoring"] = "denied"; P.apply_active(rt, pr, "us")
T(fr.icon(rt)[2] == "input_monitoring" and rt.engine.mode == "OFF", "a pair does not override a revoked permission")
# lose, regain and lose again before the notice: one entry
a = Fake({k2: "granted" for k2 in ORDER}); fr = F.FirstRun(a)
a.st["accessibility"] = "denied"; fr.refresh(); a.st["accessibility"] = "granted"; fr.refresh(); a.st["accessibility"] = "denied"; fr.refresh()
T(fr.revoked == ["accessibility"], "a repeated loss before the notice is one entry")
# a denial is forgotten when the permission is granted, also for a later loss
a = Fake(answers={"input_monitoring": "denied"}); fr = F.FirstRun(a); fr.acknowledge(); fr.request_current()
T(fr.view()["denied"], "denied")
a.st["input_monitoring"] = "granted"; fr.refresh(); a.st["input_monitoring"] = "denied"; fr.refresh()
T(fr.view()["permission"] == "input_monitoring" and not fr.view()["denied"], "a later loss does not show the old denial")
# a word in progress when a permission is lost is not converted after the permission returns
a = Fake({k2: "granted" for k2 in ORDER}); fr = F.FirstRun(a); rt, f = new(); fr.apply(rt)
typed(rt, f, "ghb", 100); a.st["accessibility"] = "denied"; fr.apply(rt); a.st["accessibility"] = "granted"; fr.apply(rt); rt.on_gate(L.GATE_ALLOW)
typed(rt, f, "dtn", 110); space(rt, f, 114)
T(f.text == "ghbdtn ", f"the half word before a loss is not converted ({f.text!r})")
# repeated applies while a permission is missing break the engine once, not every time
a = Fake(); fr = F.FirstRun(a); rt, f = new(); seen = []; orig = rt.engine.on_event
rt.engine.on_event = lambda e, *x, **y: (seen.append(e.kind), orig(e, *x, **y))[1]
for _ in range(4): fr.apply(rt)
T(seen.count("break") == 1, f"one break for one loss ({seen})")
# no instance lock and a missing permission: the icon names what Runtime.explain gives (instance), not a permission
a = Fake(); fr = F.FirstRun(a); rt, f = new(); rt.instance_ok = False
T(fr.icon(rt) == ("Off", ["instance"], None), "the permission is named only when it is the reason shown")
# the word typed while a permission is missing is neither recorded nor converted; after the grant a new word is converted
a = Fake(); fr = F.FirstRun(a); rt, f = new(); fr.apply(rt)
typed(rt, f, "ghbdtn", 100); space(rt, f, 106)
T(f.text == "ghbdtn " and rt.engine.run == [] and rt.engine.mode == "OFF", "no permission: nothing recorded, nothing converted")
for k2 in ORDER: a.st[k2] = "granted"
fr.apply(rt); f2 = L.SimField("", M1); rt.on_focus("A", f2, "AUTO"); rt.on_gate(L.GATE_ALLOW)
typed(rt, f2, "ghbdtn", 1000); space(rt, f2, 1006)
T("привет" in f2.text, f"after all grants a new word is converted ({f2.text!r})")
a.st["post_event"] = "denied"; fr.apply(rt); typed(rt, f2, "ghbdtn", 2000); space(rt, f2, 2006)
T(f2.text.endswith("ghbdtn ") and rt.engine.mode == "OFF", "after a revoke the next word is not converted")
print(f"OK ({CHECKS} first run checks; fake permission adapter, no operating system call; the real prompts, panes and revocation are NOT RUN)")
