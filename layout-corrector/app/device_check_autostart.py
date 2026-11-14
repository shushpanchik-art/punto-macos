"""Reproducible check of the autostart descriptions on a REAL device. Default: dry run (prints what it would do, touches nothing).
  python3 device_check_autostart.py                 -> dry run on any OS
  python3 device_check_autostart.py --macos-lint    -> macOS only: writes a plist into a NEW temporary directory and runs `plutil -lint` on it
  python3 device_check_autostart.py --windows-run   -> Windows only: creates, reads back and deletes ONE test value (random name) under HKCU Run
Nothing is loaded into launchd, no login item is registered, the product's own value name is never used. Expected output: lines starting with PASS.
On Linux (or with the wrong flag for the OS) it prints NOT RUN and exits 0."""
import os, plistlib, secrets, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfautostart as A

def main(argv):
    flags = set(argv)
    if not flags <= {"--macos-lint", "--windows-run"}:
        print("unknown flag"); return 2
    d = A.launch_agent("com.example.layoutcorrector.check", "/Applications/Example.app/Contents/MacOS/example")
    print("DRY: plist would contain keys", sorted(d)); print("DRY: windows command would be", A.windows_run_command("C:\\Example\\example.exe"))
    rc = 0
    if "--macos-lint" in flags:
        if sys.platform != "darwin": print("NOT RUN: macOS only")
        else:
            tmp = tempfile.mkdtemp(prefix="lfcheck_"); p = A.write_launch_agent(tmp, d)
            r = subprocess.run(["plutil", "-lint", p], capture_output=True, text=True)
            print(("PASS" if r.returncode == 0 else "FAIL") + ": plutil -lint " + r.stdout.strip()); rc |= r.returncode != 0
            print("temporary directory (delete it yourself):", tmp)
    if "--windows-run" in flags:
        if sys.platform != "win32": print("NOT RUN: Windows only")
        else:
            name = "LCCheck" + secrets.token_hex(6); reg = A.WinRegistry(); exe = "C:\\Example\\example.exe"
            try:
                cmd = A.install_run_value(reg, exe, name); ok = reg.get(name) == cmd
            finally:
                gone = A.uninstall_run_value(reg, exe, name)
            ok = ok and gone and reg.get(name) is None
            print(("PASS" if ok else "FAIL") + f": test value {name} created, read back, deleted"); rc |= not ok
    return rc
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
