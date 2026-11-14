"""Autostart DESCRIPTIONS for the process supervisor (portable generation only).

macOS: a launchd agent property list (keys checked against launchd.plist(5): Label, ProgramArguments, RunAtLoad, KeepAlive/SuccessfulExit,
ThrottleInterval, LimitLoadToSessionType, StandardOutPath, StandardErrorPath, ExitTimeOut). It is a DESCRIPTION: nothing is registered or loaded here.
The specification says "login item"; registering one needs SMAppService (native, macOS 13+) which Python cannot call. This module therefore only
produces the agent plist that an SMAppService agent registration would point at. That choice is open for the requester (see the matrix).
Windows: the per-user Run value (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, value LayoutCorrector). Not verified against Microsoft
documentation in this session. Registry access goes through a backend object; the real `winreg` backend is compiled only and is never used by tests.

Safety: files are written only into a directory the caller names; the real user and system launchd directories are refused unless `allow_real=True`
(no test passes it). No environment variables, no user names, no typed text, no secrets in any generated description.
"""
import os
import plistlib
import re
import tempfile

LABEL_RE = re.compile(r"^[A-Za-z0-9]+(\.[A-Za-z0-9-]+){2,}$")           # reverse-DNS, at least three parts
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "LayoutCorrector"
SUPERVISOR_FLAG = "--supervisor"
_ALLOWED_KEYS = {"Label", "ProgramArguments", "RunAtLoad", "KeepAlive", "ThrottleInterval", "LimitLoadToSessionType", "StandardOutPath",
                 "StandardErrorPath", "ExitTimeOut"}
_REFUSED_DIRS = ("/Library/LaunchAgents", "/Library/LaunchDaemons", "/System/Library")


class AutostartError(ValueError):
    pass


# ------------------------------------------------------------------ macOS
def _mac_path_ok(p):
    return isinstance(p, str) and p.startswith("/") and len(p) <= 1024 and ".." not in p.split("/") and not any(ord(c) < 32 or c == "\x7f" for c in p)


def launch_agent(label, supervisor_path, throttle_s=10, exit_timeout_s=20):
    if not isinstance(label, str) or not LABEL_RE.fullmatch(label) or len(label) > 128:
        raise AutostartError("label must be reverse-DNS")
    if not _mac_path_ok(supervisor_path):
        raise AutostartError("supervisor path must be absolute, without '..' or control characters")
    if not (isinstance(throttle_s, int) and 5 <= throttle_s <= 3600) or not (isinstance(exit_timeout_s, int) and 1 <= exit_timeout_s <= 300):
        raise AutostartError("interval out of range")
    return {"Label": label, "ProgramArguments": [supervisor_path, SUPERVISOR_FLAG], "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": throttle_s, "LimitLoadToSessionType": "Aqua", "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null",
            "ExitTimeOut": exit_timeout_s}


def validate_launch_agent(d):
    """Allow-list check of a description (generated or read back). Returns a list of problems; empty means acceptable."""
    bad = []
    if not isinstance(d, dict):
        return ["not a dictionary"]
    for k in d:
        if k not in _ALLOWED_KEYS:
            bad.append(f"key not allowed: {k}")
    try:
        ref = launch_agent(d.get("Label"), (d.get("ProgramArguments") or [None])[0], d.get("ThrottleInterval"), d.get("ExitTimeOut"))
    except (AutostartError, TypeError, IndexError):
        return bad + ["label, path or interval invalid"]
    if d != ref:
        bad.append("differs from the generated form")
    return bad


def render_plist(d):
    if validate_launch_agent(d):
        raise AutostartError("invalid launch agent description")
    return plistlib.dumps(d, fmt=plistlib.FMT_XML, sort_keys=True)


def _is_real_dir(directory):
    real = os.path.realpath(directory)
    home = os.path.realpath(os.path.expanduser("~/Library/LaunchAgents"))
    return real == home or any(real == os.path.realpath(p) or real.startswith(os.path.realpath(p) + os.sep) for p in _REFUSED_DIRS)


def write_launch_agent(directory, d, allow_real=False):
    """Atomic write of `<Label>.plist` (mode 0644) into `directory`. Refuses the real user and system launchd directories unless allow_real."""
    text = render_plist(d)
    if not allow_real and _is_real_dir(directory):
        raise AutostartError("refusing the real launchd directory")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, d["Label"] + ".plist")
    if os.path.islink(path):
        raise AutostartError("refusing to write through a link")
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".lf-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise
    return path


def remove_launch_agent(directory, label, allow_real=False):
    """Removes only `<label>.plist` when it is a regular file whose content is exactly a valid generated description. Returns True if removed."""
    if not allow_real and _is_real_dir(directory):
        raise AutostartError("refusing the real launchd directory")
    if not isinstance(label, str) or not LABEL_RE.fullmatch(label):
        raise AutostartError("label must be reverse-DNS")
    path = os.path.join(directory, label + ".plist")
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as f:
            d = plistlib.loads(f.read())
    except Exception:
        return False
    if validate_launch_agent(d) or d.get("Label") != label:
        return False
    os.remove(path)
    return True


# ------------------------------------------------------------------ Windows
_WIN_PATH = re.compile(r'^[A-Za-z]:\\[^\x00-\x1f"%&|<>^()!;,=]+$')


def windows_run_command(exe_path):
    if (not isinstance(exe_path, str) or len(exe_path) > 260 or not _WIN_PATH.fullmatch(exe_path) or ".." in exe_path.split("\\")
            or not exe_path.lower().endswith(".exe")):
        raise AutostartError("executable path must be an absolute drive path to an .exe without quotes, percent signs or shell characters")
    return '"%s" %s' % (exe_path, SUPERVISOR_FLAG)


def render_reg_text(exe_path, value_name=RUN_VALUE):
    """Text for a human to review; it is never imported by this code."""
    cmd = windows_run_command(exe_path)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value_name):
        raise AutostartError("value name")
    esc = cmd.replace("\\", "\\\\").replace('"', '\\"')
    return ('Windows Registry Editor Version 5.00\r\n\r\n[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run]\r\n"%s"="%s"\r\n'
            % (value_name, esc))


class MemoryRegistry:
    """Test double with the same three methods as the real backend: only the Run key, only string values."""
    def __init__(self): self.values = {}
    def get(self, name): return self.values.get(name)
    def set(self, name, data): self.values[name] = data
    def delete(self, name): return self.values.pop(name, None) is not None


class WinRegistry:  # pragma: no cover - compiled only, never run by the tests
    def _key(self, access):
        import winreg
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, access)
    def get(self, name):
        import winreg
        with self._key(winreg.KEY_READ) as k:
            try: return winreg.QueryValueEx(k, name)[0]
            except FileNotFoundError: return None
    def set(self, name, data):
        import winreg
        with self._key(winreg.KEY_SET_VALUE) as k: winreg.SetValueEx(k, name, 0, winreg.REG_SZ, data)
    def delete(self, name):
        import winreg
        with self._key(winreg.KEY_SET_VALUE) as k:
            try: winreg.DeleteValue(k, name); return True
            except FileNotFoundError: return False


def install_run_value(backend, exe_path, value_name=RUN_VALUE):
    cmd = windows_run_command(exe_path)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value_name):
        raise AutostartError("value name")
    backend.set(value_name, cmd)
    return cmd


def uninstall_run_value(backend, exe_path, value_name=RUN_VALUE):
    """Deletes the value only if it still holds exactly the command this program would write (never a value someone else changed)."""
    if backend.get(value_name) != windows_run_command(exe_path):
        return False
    return backend.delete(value_name)
