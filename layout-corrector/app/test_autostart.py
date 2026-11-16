"""Autostart descriptions: generation, allow-list, refusal of real directories, isolated temp-dir writes, fake registry. Nothing is registered, loaded
or imported anywhere; real launchd / registry / login-item behaviour is NOT RUN."""
import os, plistlib, stat, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfautostart as A
CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
def raises(fn, exc=A.AutostartError):
    try: fn()
    except exc: return True
    return False
EXE = "/Applications/LayoutCorrector.app/Contents/MacOS/lc-supervisor"; LAB = "com.example.layoutcorrector"
d = A.launch_agent(LAB, EXE)
T(d["ProgramArguments"] == [EXE, "--supervisor"] and d["RunAtLoad"] is True and d["KeepAlive"] == {"SuccessfulExit": False}, "program, run at load, restart only after a non-zero exit")
T(d["StandardOutPath"] == d["StandardErrorPath"] == "/dev/null" and "EnvironmentVariables" not in d and "UserName" not in d and "WatchPaths" not in d, "no output file, no environment, no user")
T(set(d) <= A._ALLOWED_KEYS and A.validate_launch_agent(d) == [], "generated form passes the allow-list")
T(plistlib.loads(A.render_plist(d)) == d, "the rendered plist reads back identically")
for bad in ("", "x", "a.b", "com.example.", "com.example.a b", "com.example.a;rm", "com.example.\u0430", "com.example.a\n", None, 5, "c" * 130 + ".a.b"):
    T(raises(lambda: A.launch_agent(bad, EXE)), f"label refused: {bad!r}")
for bad in ("", "relative/lc", "/a/../b", "/a\x00b", "/a\nb", "/" + "a" * 1100, None, ["x"]):
    T(raises(lambda: A.launch_agent(LAB, bad)), f"path refused: {bad!r}")
for v in (4, 3601, 1.5, "10", None, True if False else 0):
    T(raises(lambda: A.launch_agent(LAB, EXE, throttle_s=v)), f"throttle refused: {v!r}")
T(raises(lambda: A.launch_agent(LAB, EXE, exit_timeout_s=0)), "exit timeout refused")
for k, v in (("EnvironmentVariables", {"X": "1"}), ("WatchPaths", ["/tmp"]), ("UserName", "root"), ("StandardOutPath", "/tmp/x.log"), ("KeepAlive", True), ("RunAtLoad", False), ("ProgramArguments", [EXE, "--engine"]), ("Program", "/bin/sh")):
    x = dict(d); x[k] = v
    T(A.validate_launch_agent(x) != [], f"allow-list catches {k}")
    T(raises(lambda: A.render_plist(x)), f"render refuses {k}")
T(A.validate_launch_agent([]) != [] and A.validate_launch_agent({}) != [], "non-dict and empty are refused")
T("--manual-only" not in " ".join(d["ProgramArguments"]), "the manual-only flag is the supervisor's decision, never static")
# isolated writes
tmp = tempfile.mkdtemp(prefix="lfauto_"); agents = os.path.join(tmp, "LaunchAgents")
p = A.write_launch_agent(agents, d)
T(p == os.path.join(agents, LAB + ".plist") and stat.S_IMODE(os.stat(p).st_mode) == 0o644 and plistlib.load(open(p, "rb")) == d, "written atomically, mode 0644, content exact")
T(sorted(os.listdir(agents)) == [LAB + ".plist"], "no temporary file left")
A.write_launch_agent(agents, d); T(sorted(os.listdir(agents)) == [LAB + ".plist"], "writing again replaces")
for real in (os.path.expanduser("~/Library/LaunchAgents"), "/Library/LaunchAgents", "/Library/LaunchDaemons", "/System/Library/LaunchAgents", os.path.expanduser("~/Library/../Library/LaunchAgents")):
    T(raises(lambda: A.write_launch_agent(real, d)), f"real directory refused (write): {real}")
    T(raises(lambda: A.remove_launch_agent(real, LAB)), f"real directory refused (remove): {real}")
os.symlink(os.path.expanduser("~/Library/LaunchAgents"), os.path.join(tmp, "alias"))
T(raises(lambda: A.write_launch_agent(os.path.join(tmp, "alias"), d)), "a link to the real directory is refused too")
# the link case for the file itself
lk = os.path.join(tmp, "L"); os.makedirs(lk); victim = os.path.join(tmp, "victim"); open(victim, "w").write("keep")
os.symlink(victim, os.path.join(lk, LAB + ".plist"))
T(raises(lambda: A.write_launch_agent(lk, d)) and open(victim).read() == "keep", "writing through a link is refused, target untouched")
T(A.remove_launch_agent(lk, LAB) is False and os.path.exists(victim), "removal ignores a link")
# removal is exact
foreign = os.path.join(agents, "com.example.other.plist"); plistlib.dump({"Label": "com.example.other", "ProgramArguments": ["/bin/sh"]}, open(foreign, "wb"))
T(A.remove_launch_agent(agents, "com.example.other") is False and os.path.exists(foreign), "a foreign plist is never removed")
edited = dict(d); edited["ProgramArguments"] = ["/bin/sh", "-c", "x"]; plistlib.dump(edited, open(os.path.join(agents, LAB + ".plist"), "wb"))
T(A.remove_launch_agent(agents, LAB) is False and os.path.exists(os.path.join(agents, LAB + ".plist")), "a modified own plist is left for the user")
open(os.path.join(agents, LAB + ".plist"), "wb").write(b"not a plist")
T(A.remove_launch_agent(agents, LAB) is False, "garbage is left")
A.write_launch_agent(agents, d)
T(A.remove_launch_agent(agents, LAB) is True and os.listdir(agents) == ["com.example.other.plist"], "the exact own file is removed, nothing else")
T(A.remove_launch_agent(agents, LAB) is False, "removing twice is harmless")
T(raises(lambda: A.remove_launch_agent(agents, "../x")), "label with path parts refused")
# Windows
EXEW = "C:\\Program Files\\LayoutCorrector\\lc.exe"
T(A.windows_run_command(EXEW) == '"C:\\Program Files\\LayoutCorrector\\lc.exe" --supervisor', "quoted path plus the supervisor flag")
for bad in ("lc.exe", "C:lc.exe", "\\\\server\\share\\lc.exe", "C:\\a\\..\\b.exe", 'C:\\a"b.exe', "C:\\%TEMP%\\a.exe", "C:\\a&calc.exe", "C:\\a|b.exe", "C:\\a;b.exe", "C:\\a\nb.exe", "C:\\a\\b.bat", "C:\\" + "a" * 300 + ".exe", None, 5, "C:\\a^b.exe", "C:\\a(b).exe"):
    T(raises(lambda: A.windows_run_command(bad)), f"windows path refused: {bad!r}")
reg = A.render_reg_text(EXEW)
T(reg.startswith("Windows Registry Editor Version 5.00") and "[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run]" in reg and '"LayoutCorrector"="\\"C:\\\\Program Files' in reg, "review text is escaped and names only the Run key")
T(raises(lambda: A.render_reg_text(EXEW, 'x"=')), "value name restricted")
m = A.MemoryRegistry(); m.values["OtherApp"] = "keep"
cmd = A.install_run_value(m, EXEW)
T(m.values == {"OtherApp": "keep", "LayoutCorrector": cmd}, "install touches only its own value")
T(A.uninstall_run_value(m, EXEW) is True and m.values == {"OtherApp": "keep"}, "uninstall deletes only its own value")
T(A.uninstall_run_value(m, EXEW) is False, "uninstall again is harmless")
m.values["LayoutCorrector"] = '"D:\\other.exe" --x'
T(A.uninstall_run_value(m, EXEW) is False and "LayoutCorrector" in m.values, "a value someone changed is left alone")
T(raises(lambda: A.install_run_value(m, "C:\\a.bat")) and raises(lambda: A.install_run_value(m, EXEW, "bad name")), "install validates before it writes")
T(A.RUN_KEY.endswith("CurrentVersion\\Run") and A.RUN_KEY.startswith("HKCU"), "the key is the per-user Run key")
# no secrets or text in anything generated
blob = A.render_plist(d).decode() + reg + cmd
T(not any(w in blob.lower() for w in ("password", "token", "secret", "ghbdtn")) and "%" not in cmd, "generated descriptions carry no secret-like words and no variables")
# ---- fault injection (audit 4): failing writes leave the old file and no temporary file; no false success; a repeat works
import builtins, shutil as _sh
_dirA = tempfile.mkdtemp(prefix="lfas_"); LABEL = "com.example.layoutcorrector"; EXE_ = "/Applications/LayoutCorrector.app/Contents/MacOS/lc-supervisor"
good_d = A.launch_agent(LABEL, EXE_); good_text = A.render_plist(good_d)
pp = A.write_launch_agent(_dirA, good_d); T(open(pp, "rb").read() == good_text, "baseline write")
def listing(): return sorted(os.listdir(_dirA))
d2_ = A.launch_agent(LABEL, EXE_.replace("lc-supervisor", "lc-supervisor2")) if False else None
def inject(target, name, exc=OSError):
    real_ = getattr(target, name)
    def f(*a, **k): raise exc("injected")
    setattr(target, name, f)
    return lambda: setattr(target, name, real_)
other = dict(good_d)
for what, tgt, nm in (("replace", os, "replace"), ("fsync", os, "fsync"), ("chmod", os, "chmod")):
    undo = inject(tgt, nm)
    try: r = raises(lambda: A.write_launch_agent(_dirA, other), OSError)
    finally: undo()
    T(r and open(pp, "rb").read() == good_text and listing() == [LABEL + ".plist"], f"{what} fails: the old description is intact and no temporary file is left")
# a failing write in the middle of the data
class Half:
    def __init__(self, f): self.f = f
    def write(self, b): self.f.write(b[:10]); raise OSError("injected")
    def __getattr__(self, n): return getattr(self.f, n)
    def __enter__(self): return self
    def __exit__(self, *a): self.f.close()
_fd = os.fdopen
os.fdopen = lambda fd, mode="r", *a, **k: Half(_fd(fd, mode, *a, **k))
try: r = raises(lambda: A.write_launch_agent(_dirA, other), OSError)
finally: os.fdopen = _fd
T(r and open(pp, "rb").read() == good_text and listing() == [LABEL + ".plist"], "a partial write: the old description is intact, the partial temporary file is removed")
# a temporary file that cannot be removed is the only thing that may remain, and the error is still the original one
undo1 = inject(os, "replace"); undo2 = inject(os, "remove")
try: r = raises(lambda: A.write_launch_agent(_dirA, other), OSError)
finally: undo1(); undo2()
T(r and open(pp, "rb").read() == good_text, "replace and remove both fail: the original error is raised, the old description is intact")
for n in listing():
    if n.startswith(".lf-"): os.remove(os.path.join(_dirA, n))
# silent failure: replace returns but nothing was written -> no false success
_rp = os.replace
os.replace = lambda s_, d_, *a: None
_dirN = tempfile.mkdtemp(prefix="lfas_")
try: r = raises(lambda: A.write_launch_agent(_dirN, good_d), A.AutostartError)
finally: os.replace = _rp
T(r and os.listdir(_dirN) == [], "a replace that did nothing is reported as a failure, not as a written description, and its temporary file is removed")
_sh.rmtree(_dirN, ignore_errors=True)
# a repeat after a failure works
T(A.write_launch_agent(_dirA, good_d) == pp and open(pp, "rb").read() == good_text and listing() == [LABEL + ".plist"], "a repeat after the failures works")
# removal: a file that cannot be read is NOT 'absent'
_open = builtins.open
def _op(f, mode="r", *a, **k):
    if str(f) == pp and "r" in mode and "b" in mode: raise OSError("injected")
    return _open(f, mode, *a, **k)
builtins.open = _op
try: r = raises(lambda: A.remove_launch_agent(_dirA, LABEL), A.AutostartError)
finally: builtins.open = _open
T(r and os.path.exists(pp), "an unreadable description is a failure of the removal, not 'absent'; the file is untouched")
# a failing remove raises and keeps the file; a file that disappears meanwhile is 'absent'
undo = inject(os, "remove")
try: r = raises(lambda: A.remove_launch_agent(_dirA, LABEL), OSError)
finally: undo()
T(r and os.path.exists(pp), "a failing os.remove is raised, the file stays")
_rm = os.remove
def gone(p, *a): _rm(p, *a); raise FileNotFoundError("gone")
os.remove = gone
try: r = A.remove_launch_agent(_dirA, LABEL)
finally: os.remove = _rm
T(r is False and not os.path.exists(pp), "removed by someone else in between: nothing left, reported as not removed by us")
T(A.write_launch_agent(_dirA, good_d) == pp and A.remove_launch_agent(_dirA, LABEL) is True and A.remove_launch_agent(_dirA, LABEL) is False, "a repeat after the failures: removed once, then absent")
# a description that is not valid plist data is 'not ours' (False), still not an error
open(pp, "wb").write(b"\x00\x01 not a plist")
T(A.remove_launch_agent(_dirA, LABEL) is False and os.path.exists(pp), "a file that is not a plist is not ours: left alone")
os.remove(pp)
_sh.rmtree(_dirA, ignore_errors=True)
# ---- the Run value: no false success
class Lying(A.MemoryRegistry):
    def set(self, name, data): pass                       # says nothing, stores nothing
class Sticky(A.MemoryRegistry):
    def delete(self, name): return True                   # says deleted, the value stays
class Failing(A.MemoryRegistry):
    def set(self, name, data): raise OSError("injected")
    def delete(self, name): raise OSError("injected")
WE = "C:\\Program Files\\LC\\lc.exe"
T(raises(lambda: A.install_run_value(Lying(), WE)), "a backend that does not store the value: the install is a failure, not a success")
rg = Sticky(); rg.values[A.RUN_VALUE] = A.windows_run_command(WE)
T(raises(lambda: A.uninstall_run_value(rg, WE)), "a backend that says deleted and keeps the value: the removal is a failure")
T(raises(lambda: A.install_run_value(Failing(), WE), OSError) and raises(lambda: A.uninstall_run_value(Failing(), WE), OSError) is False, "a failing set raises; a failing delete is not reached when the value is not ours")
fg = Failing(); fg.values[A.RUN_VALUE] = A.windows_run_command(WE)
T(raises(lambda: A.uninstall_run_value(fg, WE), OSError) and A.RUN_VALUE in fg.values, "a failing delete raises and the value stays")
class Raced(A.MemoryRegistry):
    def delete(self, name): self.values.pop(name, None); return False          # someone else removed it between the read and the delete
rc = Raced(); rc.values[A.RUN_VALUE] = A.windows_run_command(WE)
T(A.uninstall_run_value(rc, WE) is False and rc.values == {}, "a value removed by someone else in between: the answer is not 'removed by us'")
mr = A.MemoryRegistry(); A.install_run_value(mr, WE); T(A.install_run_value(mr, WE) == A.windows_run_command(WE) and len(mr.values) == 1, "a repeat install changes nothing")
import shutil; shutil.rmtree(tmp)
print(f"OK ({CHECKS} autostart description checks; generation and temp-dir writes only; no launchd, login item or registry behaviour checked)")
