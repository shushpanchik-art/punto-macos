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
import shutil; shutil.rmtree(tmp)
print(f"OK ({CHECKS} autostart description checks; generation and temp-dir writes only; no launchd, login item or registry behaviour checked)")
