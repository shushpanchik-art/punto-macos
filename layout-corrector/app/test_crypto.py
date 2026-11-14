"""lfcrypto: framing, authentication, failure mapping and the refusal to run without a backend, through FAKE backends only.
The Windows DPAPI and macOS Keychain backends are compiled here, never run (Linux). Nothing here is an OS check."""
import hashlib, hmac, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfcrypto as C
import lfstore as S

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
def raises(fn, exc):
    try: fn()
    except exc as e: return type(e)
    except Exception as e: return type(e)
    return None

# ---------------------------------------------------------------- fake DPAPI: reversible per-"user", NOT encryption
class FakeUser:
    def __init__(self, name): self.name = name
class FakeDpapi:
    def __init__(self, user="alice", fail=None):
        self.user, self.fail, self.calls = user, fail, []
    def _k(self, entropy): return hashlib.sha256(self.user.encode() + b"|" + entropy).digest()
    def protect(self, data, entropy):
        self.calls.append(("protect", entropy))
        if self.fail == "protect": raise OSError("boom")
        k = self._k(entropy); body = bytes(b ^ k[i % 32] for i, b in enumerate(data))
        return b"BLOB" + hashlib.sha256(k + body).digest()[:8] + body
    def unprotect(self, blob, entropy):
        self.calls.append(("unprotect", entropy))
        if self.fail == "unprotect": raise OSError("boom")
        if self.fail == "api5":
            e = OSError("denied"); e.winerror = 5; raise e
        if not blob.startswith(b"BLOB") or len(blob) < 12: raise C.DecryptError("bad blob")
        k = self._k(entropy); chk, body = blob[4:12], blob[12:]
        if hashlib.sha256(k + body).digest()[:8] != chk: raise C.DecryptError("other user or damaged")
        return bytes(b ^ k[i % 32] for i, b in enumerate(body))

b = FakeDpapi(); c = C.DpapiCipher(b)
msg = json.dumps([["en2ru", "ghbdtn"]]).encode()
env = c.encrypt(msg)
T(env.startswith(b"DP1") and b"ghbdtn" not in env and c.decrypt(env) == msg, "DPAPI: round trip, header, the words are not in the envelope")
T(b.calls[0] == ("protect", C.DPAPI_ENTROPY) and b.calls[1] == ("unprotect", C.DPAPI_ENTROPY), "DPAPI: the domain label is passed both ways")
T(c.decrypt(c.encrypt(b"")) == b"", "DPAPI: empty data")
for label, bad in (("no header", b"XX1abc"), ("only the header", b"DP1"), ("empty", b""), ("wrong header", b"KC1" + env[3:])):
    T(issubclass(raises(lambda: c.decrypt(bad), BaseException), ValueError), f"DPAPI: {label} is a ValueError, not an availability error")
flipped = bytearray(env); flipped[-1] ^= 1
T(issubclass(raises(lambda: c.decrypt(bytes(flipped)), BaseException), ValueError), "DPAPI: a damaged blob is a ValueError")
T(issubclass(raises(lambda: C.DpapiCipher(FakeDpapi("bob")).decrypt(env), BaseException), ValueError), "DPAPI: another user's blob is a ValueError")
T(raises(lambda: C.DpapiCipher(FakeDpapi(fail="protect")).encrypt(b"x"), S.CipherUnavailable) is S.CipherUnavailable, "DPAPI: an API error on protect is CipherUnavailable")
T(raises(lambda: C.DpapiCipher(FakeDpapi(fail="unprotect")).decrypt(env), S.CipherUnavailable) is S.CipherUnavailable, "DPAPI: an API error on unprotect is CipherUnavailable")
T(raises(lambda: C.DpapiCipher(FakeDpapi(fail="api5")).decrypt(env), S.CipherUnavailable) is S.CipherUnavailable, "DPAPI: access denied (5) is CipherUnavailable, not 'damaged'")
class InvalidData(FakeDpapi):
    def unprotect(self, blob, entropy):
        e = OSError("invalid"); e.winerror = 13; raise e
T(issubclass(raises(lambda: C.DpapiCipher(InvalidData()).decrypt(env), BaseException), ValueError), "DPAPI: ERROR_INVALID_DATA (13) is 'not decryptable'")

# ---------------------------------------------------------------- fake Keychain + fake AES (a keystream; NOT AES)
class FakeKeychain:
    def __init__(self, master=None, fail=None):
        self.master, self.fail, self.created, self.aes_calls = master, fail, 0, []
    def get_master(self, create):
        if self.fail == "keychain": raise OSError("locked")
        if self.master is None and create:
            self.master, self.created = bytes(range(32)), self.created + 1
        return self.master
    def aes_cbc(self, encrypt, key, iv, data):
        self.aes_calls.append(encrypt)
        if self.fail == "aes": raise OSError("CCCrypt")
        ks = b"".join(hashlib.sha256(key + iv + bytes([i])).digest() for i in range(len(data) // 32 + 2))
        if encrypt:
            pad = 16 - len(data) % 16; data = data + bytes([pad]) * pad
            return bytes(x ^ y for x, y in zip(data, ks))
        pt = bytes(x ^ y for x, y in zip(data, ks))
        if not 1 <= pt[-1] <= 16 or pt[-pt[-1]:] != bytes([pt[-1]]) * pt[-1]: raise C.DecryptError("padding")
        return pt[:-pt[-1]]

k = FakeKeychain(); kc = C.KeychainCipher(k)
env = kc.encrypt(msg)
T(env.startswith(b"KC1") and b"ghbdtn" not in env and kc.decrypt(env) == msg and k.created == 1, "Keychain: round trip, header, one master created")
T(len(env) == 3 + 16 + 32 + ((len(msg) // 16) + 1) * 16, "Keychain: envelope = header + IV + padded ciphertext + 32-byte tag")
env2 = kc.encrypt(msg)
T(env2 != env and k.created == 1, "Keychain: a fresh IV for every encryption, the master is reused")
T(kc.decrypt(kc.encrypt(b"")) == b"", "Keychain: empty data")
# authentication first
ek, mk = C.KeychainCipher._keys(bytes(range(32)))
T(ek != mk and len(ek) == len(mk) == 32, "Keychain: the encryption key and the MAC key differ")
for pos in (0, 5, 3 + 16 + 2, len(env) - 40, len(env) - 1):
    t = bytearray(env); t[pos] ^= 0x01
    k.aes_calls.clear()
    r = raises(lambda: kc.decrypt(bytes(t)), BaseException)
    T(r is not None and issubclass(r, ValueError), f"Keychain: a bit flipped at {pos} is a ValueError")
    T(k.aes_calls == [], f"Keychain: a bit flipped at {pos}: nothing was decrypted before the tag was checked")
for label, bad in (("truncated", env[:-1]), ("short", env[:20]), ("empty", b""), ("wrong header", b"DP1" + env[3:]), ("not a block multiple", env + b"x")):
    r = raises(lambda: kc.decrypt(bad), BaseException)
    T(r is not None and issubclass(r, ValueError), f"Keychain: {label} is a ValueError")
r = raises(lambda: C.KeychainCipher(FakeKeychain(master=bytes(32))).decrypt(env), BaseException)
T(r is not None and issubclass(r, ValueError), "Keychain: another master key fails the tag: ValueError")
nokey = FakeKeychain()
r = raises(lambda: C.KeychainCipher(nokey).decrypt(env), BaseException)
T(r is not None and issubclass(r, ValueError) and nokey.created == 0, "Keychain: a missing master on decrypt is 'not decryptable' and creates NOTHING")
for fail in ("keychain", "aes"):
    T(raises(lambda: C.KeychainCipher(FakeKeychain(fail=fail)).encrypt(b"x"), S.CipherUnavailable) is S.CipherUnavailable, f"Keychain: an API error ({fail}) on encrypt is CipherUnavailable")
T(raises(lambda: C.KeychainCipher(FakeKeychain(fail="keychain")).decrypt(env), S.CipherUnavailable) is S.CipherUnavailable, "Keychain: a locked keychain on decrypt is CipherUnavailable")
T(raises(lambda: C.KeychainCipher(FakeKeychain(master=b"short")).encrypt(b"x"), S.CipherUnavailable) is S.CipherUnavailable, "Keychain: a master of the wrong size is refused")
T(raises(lambda: C.KeychainCipher(FakeKeychain(), urandom=lambda n: b"x").encrypt(b"x"), S.CipherUnavailable) is S.CipherUnavailable, "Keychain: a short IV is refused")
# a padding failure behind a valid tag (cannot happen from our own encrypt): the backend's verdict is kept
class BadPad(FakeKeychain):
    def aes_cbc(self, encrypt, key, iv, data):
        if not encrypt: raise C.DecryptError("padding")
        return super().aes_cbc(encrypt, key, iv, data)
bp = C.KeychainCipher(BadPad()); e3 = bp.encrypt(b"abc")
r = raises(lambda: bp.decrypt(e3), BaseException)
T(r is not None and issubclass(r, ValueError), "Keychain: a padding verdict from the backend is a ValueError")

# ---------------------------------------------------------------- no fallback, no test cipher
T(raises(lambda: C.default_cipher("linux"), S.CipherUnavailable) is S.CipherUnavailable, "default_cipher: no key store on linux: CipherUnavailable, no plaintext fallback")
T(raises(lambda: C.default_cipher("freebsd"), S.CipherUnavailable) is S.CipherUnavailable, "default_cipher: no binding for another system")
T(isinstance(C.default_cipher("win32", {"win32": FakeDpapi()}), C.DpapiCipher) and isinstance(C.default_cipher("darwin", {"darwin": FakeKeychain()}), C.KeychainCipher), "default_cipher: the right class per platform")
T(not isinstance(C.default_cipher("win32", {"win32": FakeDpapi()}), S.TestOnlyCipher), "default_cipher never returns the test double")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lfcrypto.py"), encoding="utf-8").read()
T("TestOnly" not in src and "allow_test_cipher" not in src, "lfcrypto.py does not mention the test double")
T(raises(lambda: C._WinDpapi(), S.CipherUnavailable) is S.CipherUnavailable and raises(lambda: C._MacKeychain(), S.CipherUnavailable) is S.CipherUnavailable, "the real backends refuse to start on the wrong system (here: Linux)")
T(raises(lambda: C.DpapiCipher(), S.CipherUnavailable) is S.CipherUnavailable and raises(lambda: C.KeychainCipher(), S.CipherUnavailable) is S.CipherUnavailable, "a cipher without a backend refuses, it does not degrade")
compile(src, "lfcrypto.py", "exec"); T(True, "lfcrypto.py compiles (the ctypes backends are NOT run)")

# ---------------------------------------------------------------- the store with these ciphers
def mk_store(cipher):
    d = tempfile.mkdtemp(prefix="lfcrypto_"); return d, S.Store(os.path.join(d, "settings.json"), cipher)
for name, cipher in (("DPAPI", C.DpapiCipher(FakeDpapi())), ("Keychain", C.KeychainCipher(FakeKeychain()))):
    d, st = mk_store(cipher)
    state = st.load(); state.exceptions = [("en2ru", "ghbdtn"), ("ru2en", "руддщ")]
    T(st.save(state), f"{name}: store saves")
    raw = open(st.path, encoding="utf-8").read()
    T("ghbdtn" not in raw and "руддщ" not in raw, f"{name}: the words are not in the file")
    T(S.Store(st.path, cipher).load().exceptions == state.exceptions, f"{name}: the store round-trips through the cipher")
    # damaged ciphertext: the file is set aside, defaults are used
    doc = json.load(open(st.path, encoding="utf-8")); import base64
    blob = bytearray(base64.b64decode(doc["exceptions"])); blob[-1] ^= 1; doc["exceptions"] = base64.b64encode(bytes(blob)).decode()
    json.dump(doc, open(st.path, "w", encoding="utf-8"))
    s2 = S.Store(st.path, cipher); r = s2.load()
    T(r.exceptions == [] and "file_unreadable_defaults" in s2.notices and any(n.startswith("settings.json.corrupt-") for n in os.listdir(d)), f"{name}: a damaged ciphertext sets the file aside")
# an unavailable key store: the file stays exactly as it is
for name, good, bad in (("DPAPI", C.DpapiCipher(FakeDpapi()), C.DpapiCipher(FakeDpapi(fail="unprotect"))),
                        ("Keychain", C.KeychainCipher(FakeKeychain()), C.KeychainCipher(FakeKeychain(fail="keychain")))):
    d, st = mk_store(good); state = st.load(); state.exceptions = [("en2ru", "abc")]; st.save(state)
    before = open(st.path, "rb").read()
    s2 = S.Store(st.path, bad); r = s2.load()
    T(r.exceptions == [] and s2.read_only and "cipher_unavailable" in s2.notices and open(st.path, "rb").read() == before and os.listdir(d) == ["settings.json"],
      f"{name}: an unavailable key store keeps the file, sets nothing aside, writes nothing")
    T(s2.save(r) is False and open(st.path, "rb").read() == before, f"{name}: no write while it is unavailable")
    d, st = mk_store(C.DpapiCipher(FakeDpapi(fail="protect")) if name == "DPAPI" else C.KeychainCipher(FakeKeychain(fail="keychain")))
    state = S.StoreState(); state.exceptions = [("en2ru", "abc")]
    T(st.save(state) is False and not os.path.exists(st.path) and "cipher_unavailable" in st.notices and os.listdir(d) == [], f"{name}: saving without a key store writes NO file, nothing in clear")
# ---------------------------------------------------------------- the device check itself (its logic, on fakes)
import device_check_cipher as D
for name, cipher in (("DPAPI", C.DpapiCipher(FakeDpapi())), ("Keychain", C.KeychainCipher(FakeKeychain()))):
    rows = D.run_checks(cipher)
    T(len(rows) >= 15 and all(ok for _, ok, _ in rows), f"device check passes the fake {name}: {[n for n, ok, _ in rows if not ok]}")
class Identity(S.Cipher):
    def encrypt(self, d): return d
    def decrypt(self, d): return d
bad = [n for n, ok, _ in D.run_checks(Identity()) if not ok]
T("the words are not in the envelope in clear" in bad and any("changed" in n for n in bad), "device check REJECTS a cipher that does not encrypt or authenticate")
class WrongClass(S.Cipher):
    def encrypt(self, d): return b"W" + d[::-1]
    def decrypt(self, d):
        if not d.startswith(b"W"): raise KeyError("x")
        return d[1:][::-1]
T(any(not ok for _, ok, _ in D.run_checks(WrongClass())), "device check REJECTS a cipher that raises the wrong error class")
import subprocess
r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_check_cipher.py"), os.path.join(tempfile.mkdtemp(), "o.json")], capture_output=True, text=True)
T(r.returncode == 2 and "NOT RUN" in r.stdout, "on Linux the device check reports NOT RUN and writes nothing else")

print(f"OK ({CHECKS} cipher checks; fake backends only; the Windows DPAPI and macOS Keychain backends are compiled, NOT RUN)")
