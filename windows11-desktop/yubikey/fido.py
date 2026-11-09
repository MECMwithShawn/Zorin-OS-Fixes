"""The few libfido2 calls the keyring unlock needs: register a credential with hmac-secret and
read its secret back with a touch. Talks to the system libfido2 through ctypes."""
import ctypes
import os
import threading

ES256 = -7
EXT_HMAC_SECRET = 0x01
OPT_FALSE, OPT_TRUE = 1, 2
ERR_KEEPALIVE_CANCEL = 0x2d
ERR_NO_CREDENTIALS = 0x2e
ERR_PIN_REQUIRED = 0x36
ERR_ACTION_TIMEOUT = 0x3a
TIMEOUT_MS = 30_000
MAX_DEVICES = 16

_lib = None
_lock = threading.Lock()


class FidoError(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code = code

    @property
    def cancelled(self):
        return self.code in (ERR_KEEPALIVE_CANCEL, ERR_ACTION_TIMEOUT)


def lib():
    global _lib
    with _lock:
        if _lib is None:
            l = ctypes.CDLL('libfido2.so.1')
            P, I, S, B, C = ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p
            sig = {
                'fido_init': (None, [I]),
                'fido_strerr': (C, [I]),
                'fido_dev_info_new': (P, [S]),
                'fido_dev_info_free': (None, [ctypes.POINTER(P), S]),
                'fido_dev_info_manifest': (I, [P, S, ctypes.POINTER(S)]),
                'fido_dev_info_ptr': (P, [P, S]),
                'fido_dev_info_path': (C, [P]),
                'fido_dev_new': (P, []),
                'fido_dev_free': (None, [ctypes.POINTER(P)]),
                'fido_dev_open': (I, [P, B]),
                'fido_dev_close': (I, [P]),
                'fido_dev_cancel': (I, [P]),
                'fido_dev_set_timeout': (I, [P, I]),
                'fido_dev_make_cred': (I, [P, P, B]),
                'fido_dev_get_assert': (I, [P, P, B]),
                'fido_cred_new': (P, []),
                'fido_cred_free': (None, [ctypes.POINTER(P)]),
                'fido_cred_set_type': (I, [P, I]),
                'fido_cred_set_rp': (I, [P, B, B]),
                'fido_cred_set_user': (I, [P, B, S, B, B, B]),
                'fido_cred_set_clientdata_hash': (I, [P, B, S]),
                'fido_cred_set_extensions': (I, [P, I]),
                'fido_cred_set_rk': (I, [P, I]),
                'fido_cred_id_ptr': (P, [P]),
                'fido_cred_id_len': (S, [P]),
                'fido_assert_new': (P, []),
                'fido_assert_free': (None, [ctypes.POINTER(P)]),
                'fido_assert_set_rp': (I, [P, B]),
                'fido_assert_set_clientdata_hash': (I, [P, B, S]),
                'fido_assert_allow_cred': (I, [P, B, S]),
                'fido_assert_set_extensions': (I, [P, I]),
                'fido_assert_set_hmac_salt': (I, [P, B, S]),
                'fido_assert_set_up': (I, [P, I]),
                'fido_assert_count': (S, [P]),
                'fido_assert_hmac_secret_ptr': (P, [P, S]),
                'fido_assert_hmac_secret_len': (S, [P, S]),
            }
            for name, (res, args) in sig.items():
                fn = getattr(l, name)
                fn.restype, fn.argtypes = res, args
            l.fido_init(0)
            _lib = l
        return _lib


def check(code):
    if code:
        raise FidoError(code, lib().fido_strerr(code).decode(errors='replace'))


def devices():
    """Paths of the connected FIDO devices."""
    l = lib()
    infos = ctypes.c_void_p(l.fido_dev_info_new(MAX_DEVICES))
    if not infos:
        return []
    try:
        found = ctypes.c_size_t(0)
        check(l.fido_dev_info_manifest(infos, MAX_DEVICES, ctypes.byref(found)))
        return [l.fido_dev_info_path(l.fido_dev_info_ptr(infos, i)) for i in range(found.value)]
    finally:
        l.fido_dev_info_free(ctypes.byref(infos), MAX_DEVICES)


class Device:
    """An open FIDO device. `cancel()` may be called from another thread while it waits."""

    def __init__(self, path):
        l = lib()
        self.dev = ctypes.c_void_p(l.fido_dev_new())
        try:
            check(l.fido_dev_open(self.dev, path))
        except FidoError:
            l.fido_dev_free(ctypes.byref(self.dev))
            raise
        l.fido_dev_set_timeout(self.dev, TIMEOUT_MS)

    def cancel(self):
        lib().fido_dev_cancel(self.dev)

    def close(self):
        if self.dev:
            l = lib()
            l.fido_dev_close(self.dev)
            l.fido_dev_free(ctypes.byref(self.dev))
            self.dev = ctypes.c_void_p()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def register(self, rp, user, pin=None):
        """A new non-discoverable credential with hmac-secret; returns its id. One touch."""
        l = lib()
        cred = ctypes.c_void_p(l.fido_cred_new())
        try:
            cdh = os.urandom(32)
            uid = os.urandom(16)
            check(l.fido_cred_set_type(cred, ES256))
            check(l.fido_cred_set_clientdata_hash(cred, cdh, 32))
            check(l.fido_cred_set_rp(cred, rp.encode(), b'Zorin keyring unlock'))
            check(l.fido_cred_set_user(cred, uid, len(uid), user.encode(), user.encode(), None))
            check(l.fido_cred_set_extensions(cred, EXT_HMAC_SECRET))
            check(l.fido_cred_set_rk(cred, OPT_FALSE))
            check(l.fido_dev_make_cred(self.dev, cred, pin))
            return ctypes.string_at(l.fido_cred_id_ptr(cred), l.fido_cred_id_len(cred))
        finally:
            l.fido_cred_free(ctypes.byref(cred))

    def hmac_secret(self, rp, credential_id, salt):
        """The credential's hmac-secret for `salt` (32 bytes), after a touch. No PIN: the same
        credential and salt always give the same secret."""
        l = lib()
        assertion = ctypes.c_void_p(l.fido_assert_new())
        try:
            check(l.fido_assert_set_rp(assertion, rp.encode()))
            check(l.fido_assert_set_clientdata_hash(assertion, os.urandom(32), 32))
            check(l.fido_assert_allow_cred(assertion, credential_id, len(credential_id)))
            check(l.fido_assert_set_extensions(assertion, EXT_HMAC_SECRET))
            check(l.fido_assert_set_hmac_salt(assertion, salt, len(salt)))
            check(l.fido_assert_set_up(assertion, OPT_TRUE))
            check(l.fido_dev_get_assert(self.dev, assertion, None))
            if l.fido_assert_count(assertion) < 1 or l.fido_assert_hmac_secret_len(assertion, 0) != 32:
                raise FidoError(0, 'The key returned no hmac-secret')
            return ctypes.string_at(l.fido_assert_hmac_secret_ptr(assertion, 0), 32)
        finally:
            l.fido_assert_free(ctypes.byref(assertion))
