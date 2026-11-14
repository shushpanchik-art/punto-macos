"""lfcrypto.py - the OS key store behind the `Cipher` contract of lfstore (13.3, AP-5): Windows DPAPI and macOS Keychain.

STATE: written here and tested here ONLY through fake backends (framing, authentication, failure mapping, the refusal to run without a
backend). The real backends (`_WinDpapi`, `_MacKeychain`) are compiled, never imported on their OS and NEVER RUN: this repository's
environment is Linux. `app/device_check_cipher.py` is the reproducible check to run on a device (status NOT RUN until it has).

Rules kept here:
  * there is no fallback. Without a usable backend `default_cipher` raises `CipherUnavailable`; nothing is written in clear and
    the test double of lfstore is not imported or referenced in this module;
  * `CipherUnavailable` (cannot use the key store now) and `ValueError` (the key store says the data is not decryptable) are kept apart:
    the store keeps the file on the first and sets it aside on the second;
  * the key of the user is only ever used by the OS: DPAPI keeps it, the Keychain item holds a random 32-byte master key that is created
    by this program under its own service name; a key or item of any other name is never read.

Windows DPAPI: CryptProtectData / CryptUnprotectData of the current user, flag CRYPTPROTECT_UI_FORBIDDEN (no dialog), optional entropy as a
domain label (not a secret). Envelope: b"DP2" + SHA-256(blob) + the DPAPI blob.
macOS: the master key from a generic-password Keychain item (user interaction forbidden); AES-256-CBC with PKCS#7 from CommonCrypto
(`CCCrypt`, public API) under a key derived as HMAC-SHA256(master, b"enc"), authenticated by HMAC-SHA256 under HMAC-SHA256(master, b"mac")
over header, IV and ciphertext (encrypt-then-MAC, the tag is checked before anything is decrypted). Envelope: b"KC1" + IV(16) + ciphertext + tag(32).
Checked against the documentation (reading only, 2026-11-14): the parameter order of CryptProtectData/CryptUnprotectData (learn.microsoft.com);
the caller frees pbData with LocalFree; the docs name ERROR_PASSWORD_RESTRICTION for UI_FORBIDDEN and tell callers not to rely on a code to
detect tampering (hence the own checksum); the numeric value 0x1 of CRYPTPROTECT_UI_FORBIDDEN is NOT on that page (it is from dpapi.h, not
re-checked). CommonCrypto status values -4300 to -4311 and the SecKeychain* and SecBase.h declarations and constants -25300, -25299, -25308,
-25315, -25293, -128 (opensource.apple.com) match the code. The same documentation does not say when the Keychain answers "not found", and a
developer-forum thread reports errSecItemNotFound for an item that exists, so "not found" is never a verdict on the file.
The unverified parts, on purpose listed: the ctypes signatures, the OSStatus and Win32 error-code mapping, and whether the Keychain
item is created with the access control that the product wants."""
import hashlib
import hmac
import os
import sys

from lfstore import Cipher, CipherUnavailable

SERVICE = "layout-corrector"
ACCOUNT = "exception-list-key"
DPAPI_ENTROPY = b"layout-corrector/exception-list/v1"
_KC_NOT_FOUND = -25300                                      # errSecItemNotFound
_KC_DUPLICATE = -25299                                      # errSecDuplicateItem


class DecryptError(ValueError):
    """A backend's own verdict that the data is not decryptable (damaged, or for another user or key)."""


# ----------------------------------------------------------------------------------------------------------------------------
class DpapiCipher(Cipher):
    """backend: protect(data, entropy) -> bytes, unprotect(blob, entropy) -> bytes; any exception of a backend means "cannot do it now".
    The documentation of CryptUnprotectData says that "applications should not rely on a specific error code to detect data tampering"
    (ERROR_INVALID_DATA and ERROR_INVALID_PARAMETER are only named as possible), so NO Win32 code decides here whether a file is damaged.
    What decides is our own SHA-256 over the DPAPI blob, kept next to it: a mismatch is damage that no OS state can explain (ValueError).
    A matching checksum with a failing unprotect (another user or profile, a lost master key, ERROR_PASSWORD_RESTRICTION, anything)
    is CipherUnavailable: the file is kept, never set aside on a guess. The user's way out is "Delete all data"."""
    HEADER = b"DP2"

    def __init__(self, backend=None):
        self.b = backend if backend is not None else _WinDpapi()

    def encrypt(self, data: bytes) -> bytes:
        try:
            blob = self.b.protect(bytes(data), DPAPI_ENTROPY)
        except CipherUnavailable:
            raise
        except Exception as e:
            raise CipherUnavailable(f"DPAPI protect failed: {type(e).__name__}") from None
        return self.HEADER + hashlib.sha256(blob).digest() + blob

    def decrypt(self, data: bytes) -> bytes:
        n = len(self.HEADER) + 32
        if not data.startswith(self.HEADER) or len(data) <= n:
            raise ValueError("not a DPAPI envelope")
        blob = data[n:]
        if not hmac.compare_digest(hashlib.sha256(blob).digest(), data[len(self.HEADER):n]):
            raise ValueError("the DPAPI envelope is damaged")
        try:
            return self.b.unprotect(bytes(blob), DPAPI_ENTROPY)
        except CipherUnavailable:
            raise
        except Exception as e:
            code = getattr(e, "winerror", None)
            raise CipherUnavailable(f"DPAPI unprotect failed: {type(e).__name__} {code}") from None


class KeychainCipher(Cipher):
    """backend: get_master(create: bool) -> bytes | None (None only when absent and not `create`), aes_cbc(encrypt, key, iv, data) -> bytes.
    A backend raises DecryptError for a padding/decoding failure and anything else for an API error."""
    HEADER, IV, TAG = b"KC1", 16, 32

    def __init__(self, backend=None, urandom=os.urandom):
        self.b, self._rand = (backend if backend is not None else _MacKeychain()), urandom

    @staticmethod
    def _keys(master: bytes):
        if len(master) != 32:
            raise CipherUnavailable("master key of the wrong size")
        return hmac.new(master, b"enc", hashlib.sha256).digest(), hmac.new(master, b"mac", hashlib.sha256).digest()

    def encrypt(self, data: bytes) -> bytes:
        try:
            master = self.b.get_master(True)
            if master is None:
                raise CipherUnavailable("no master key could be created")
            ek, mk = self._keys(master)
            iv = self._rand(self.IV)
            if len(iv) != self.IV:
                raise CipherUnavailable("bad IV")
            body = self.HEADER + iv + self.b.aes_cbc(True, ek, iv, bytes(data))
            return body + hmac.new(mk, body, hashlib.sha256).digest()
        except CipherUnavailable:
            raise
        except Exception as e:
            raise CipherUnavailable(f"Keychain encrypt failed: {type(e).__name__}") from None

    def decrypt(self, data: bytes) -> bytes:
        n = len(self.HEADER) + self.IV + self.TAG
        if not data.startswith(self.HEADER) or len(data) < n + 16 or (len(data) - n) % 16:
            raise ValueError("not a Keychain envelope")
        try:
            master = self.b.get_master(False)
            if master is None:
                # errSecItemNotFound can also be an access-control effect, so "not found" proves nothing about a lost key: keep the file
                raise CipherUnavailable("the master key was not found in the key store; the file is kept")
            ek, mk = self._keys(master)
            body, tag = data[:-self.TAG], data[-self.TAG:]
            if not hmac.compare_digest(hmac.new(mk, body, hashlib.sha256).digest(), tag):
                raise DecryptError("authentication failed")          # checked BEFORE anything is decrypted
            iv = body[len(self.HEADER):len(self.HEADER) + self.IV]
            return self.b.aes_cbc(False, ek, iv, body[len(self.HEADER) + self.IV:])
        except (DecryptError, CipherUnavailable):
            raise
        except Exception as e:
            raise CipherUnavailable(f"Keychain decrypt failed: {type(e).__name__}") from None


def default_cipher(platform: str = None, backends: dict = None):
    """The cipher for this system, or CipherUnavailable. `backends` (tests) maps "win32" / "darwin" to a backend object."""
    platform = platform or sys.platform
    backends = backends or {}
    if platform == "win32":
        return DpapiCipher(backends.get("win32"))
    if platform == "darwin":
        return KeychainCipher(backends.get("darwin"))
    raise CipherUnavailable(f"no OS key store binding for {platform!r}")


# ---- the real backends (ctypes). COMPILED ONLY, never run here -------------------------------------------------------------
class _WinDpapi:
    def __init__(self):
        if sys.platform != "win32":
            raise CipherUnavailable("DPAPI exists only on Windows")
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        self.BLOB = BLOB
        for fn in (self.crypt32.CryptProtectData, self.crypt32.CryptUnprotectData):
            fn.restype = wintypes.BOOL
        self.crypt32.CryptProtectData.argtypes = [ctypes.POINTER(BLOB), wintypes.LPCWSTR, ctypes.POINTER(BLOB), ctypes.c_void_p,
                                                  ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
        self.crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.POINTER(BLOB), ctypes.c_void_p,
                                                    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
        self.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self.kernel32.LocalFree.restype = ctypes.c_void_p

    def _blob(self, b: bytes):
        buf = self.ct.create_string_buffer(b, len(b))
        return self.BLOB(len(b), self.ct.cast(buf, self.ct.POINTER(self.ct.c_char))), buf

    def _call(self, fn, data, entropy):
        inb, keep1 = self._blob(data)
        ent, keep2 = self._blob(entropy)
        out = self.BLOB()
        args = (self.ct.byref(inb), None, self.ct.byref(ent), None, None, 0x1, self.ct.byref(out))   # 0x1 = CRYPTPROTECT_UI_FORBIDDEN
        if not fn(*args):
            err = self.ct.get_last_error()
            raise OSError(None, "DPAPI call failed", None, err)
        try:
            return self.ct.string_at(out.pbData, out.cbData)
        finally:
            self.kernel32.LocalFree(self.ct.cast(out.pbData, self.ct.c_void_p))

    def protect(self, data, entropy):
        return self._call(self.crypt32.CryptProtectData, data, entropy)

    def unprotect(self, blob, entropy):
        return self._call(self.crypt32.CryptUnprotectData, blob, entropy)


class _MacKeychain:
    def __init__(self, service: str = SERVICE, account: str = ACCOUNT):
        if sys.platform != "darwin":
            raise CipherUnavailable("the Keychain exists only on macOS")
        import ctypes
        self.ct = ctypes
        self.sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.sys = ctypes.CDLL("/usr/lib/libSystem.dylib")
        self.service, self.account = service.encode(), account.encode()
        self.sec.SecKeychainSetUserInteractionAllowed(0)          # never show a dialog

    def _find(self):
        ct = self.ct
        n, p = ct.c_uint32(0), ct.c_void_p()
        st = self.sec.SecKeychainFindGenericPassword(None, len(self.service), self.service, len(self.account), self.account,
                                                     ct.byref(n), ct.byref(p), None)
        if st == _KC_NOT_FOUND:
            return None
        if st != 0:
            raise OSError(f"SecKeychainFindGenericPassword {st}")
        try:
            return ct.string_at(p, n.value)
        finally:
            self.sec.SecKeychainItemFreeContent(None, p)

    def get_master(self, create: bool):
        m = self._find()
        if m is not None or not create:
            return m
        new = os.urandom(32)
        st = self.sec.SecKeychainAddGenericPassword(None, len(self.service), self.service, len(self.account), self.account, 32, new, None)
        if st == _KC_DUPLICATE:
            return self._find()
        if st != 0:
            raise OSError(f"SecKeychainAddGenericPassword {st}")
        return new

    def aes_cbc(self, encrypt, key, iv, data):
        ct = self.ct
        out = ct.create_string_buffer(len(data) + 16)
        moved = ct.c_size_t(0)
        st = self.sys.CCCrypt(0 if encrypt else 1, 0, 1, key, len(key), iv, data, len(data), out, len(out), ct.byref(moved))   # AES, PKCS7
        if st in (-4304, -4303) and not encrypt:        # kCCDecodeError (bad padding), kCCAlignmentError
            raise DecryptError(f"CCCrypt {st}")
        if st != 0:
            raise OSError(f"CCCrypt {st}")
        return out.raw[:moved.value]
