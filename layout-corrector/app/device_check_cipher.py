#!/usr/bin/env python3
"""Reproducible device check of the OS key store binding (lfcrypto). Run it ON Windows (DPAPI) or on macOS (Keychain):

    python device_check_cipher.py out.json

It touches no key and no data of the user: files live in a fresh temporary directory; on macOS the master key is created under a TEST
service name `layout-corrector-selftest-<random>` (the product's own item is never read or written), and the check prints the command that
deletes that test item. DPAPI keeps nothing between runs. Result: a JSON file with one entry per check and `verdict` PASS or FAIL.
STATE: written and tested only with fake backends in this repository (test_crypto.py); NOT RUN on any device. Until a PASS file from a real
Windows and a real macOS machine exists, the real backends are `NOT RUN` and no claim about them is made."""
import json
import os
import platform
import secrets
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfcrypto as C  # noqa: E402
import lfstore as S  # noqa: E402


def run_checks(cipher):
    """Checks on any `Cipher`; returns a list of (name, ok, detail)."""
    out = []
    add = lambda n, ok, d="": out.append((n, bool(ok), d))
    msg = json.dumps([["en2ru", "ghbdtn"], ["ru2en", "руддщ"]], ensure_ascii=False).encode()
    try:
        env = cipher.encrypt(msg)
        add("encrypt returns bytes", isinstance(env, bytes) and len(env) > 0)
        add("the words are not in the envelope in clear", b"ghbdtn" not in env and "руддщ".encode() not in env)
        add("round trip", cipher.decrypt(env) == msg)
        add("two encryptions of the same data differ or are both valid", cipher.decrypt(cipher.encrypt(msg)) == msg)
        add("empty data", cipher.decrypt(cipher.encrypt(b"")) == b"")
        for label, pos in (("first byte", 0), ("middle", len(env) // 2), ("last byte", len(env) - 1)):
            t = bytearray(env); t[pos] ^= 1
            try:
                got = cipher.decrypt(bytes(t)); add(f"a changed {label} is refused", False, "decrypted without an error")
            except ValueError:
                add(f"a changed {label} is refused", True)
            except Exception as e:
                add(f"a changed {label} is refused", False, f"wrong error class {type(e).__name__}")
        for label, bad in (("truncated", env[:-1]), ("empty", b""), ("garbage", os.urandom(64))):
            try:
                cipher.decrypt(bad); add(f"{label} input is refused", False)
            except ValueError:
                add(f"{label} input is refused", True)
            except Exception as e:
                add(f"{label} input is refused", False, f"wrong error class {type(e).__name__}")
        d = tempfile.mkdtemp(prefix="lfcipher_check_")
        st = S.Store(os.path.join(d, "settings.json"), cipher)
        state = st.load(); state.exceptions = [("en2ru", "ghbdtn")]
        add("the store saves", st.save(state))
        add("the store reloads the list", S.Store(st.path, cipher).load().exceptions == [("en2ru", "ghbdtn")])
        add("no word in the file in clear", "ghbdtn" not in open(st.path, encoding="utf-8").read())
        st.delete_all()
        add("delete_all leaves the temporary directory empty", os.listdir(d) == [])
        os.rmdir(d)
    except Exception as e:
        add("no unexpected exception", False, f"{type(e).__name__}: {e}")
    return out


def main(argv):
    out = argv[1] if len(argv) > 1 else "cipher_check.json"
    service = None
    try:
        if sys.platform == "win32":
            cipher = C.DpapiCipher()
        elif sys.platform == "darwin":
            service = "layout-corrector-selftest-" + secrets.token_hex(4)
            cipher = C.KeychainCipher(C._MacKeychain(service=service))
        else:
            raise S.CipherUnavailable(f"no key store binding for {sys.platform}")
    except S.CipherUnavailable as e:
        res = {"verdict": "NOT RUN", "reason": str(e), "platform": sys.platform}
        json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
        print(res)
        return 2
    rows = run_checks(cipher)
    res = {"verdict": "PASS" if all(ok for _, ok, _ in rows) else "FAIL", "platform": sys.platform, "os": platform.platform(),
           "python": platform.python_version(), "synthetic": False, "test_service": service,
           "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in rows]}
    json.dump(res, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(res["verdict"], f"{sum(ok for _, ok, _ in rows)}/{len(rows)}")
    if service:
        print(f"Delete the test item afterwards:  security delete-generic-password -s {service} -a {C.ACCOUNT}")
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
