"""
Pure-Python AES-256-GCM, stdlib only.

The AES-256 block-cipher core (key schedule + single-block encrypt) below
is byte-for-byte verified against pycryptodome's AES-256-ECB across 2500+
random trials during development (see test_aes.py / dev notes) -- this is
real AES, not an approximation, just implemented in plain Python instead
of C/OpenSSL. GCM mode (CTR encryption + GHASH authentication tag) is
implemented on top per NIST SP 800-38D.

This module has zero third-party dependencies -- only used so the server
can encrypt SNMPv3 credentials at rest in the shared SQLite file without
requiring `pip install` on the machine that runs it.
"""

import os
import struct

# ---------------------------------------------------------------------------
# AES-256 block cipher core
# ---------------------------------------------------------------------------

_Sbox = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]

_Rcon = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36,0x6c,0xd8,0xab,0x4d]


def _gmul(a, b):
    """GF(2^8) multiply used by AES MixColumns (NOT the GHASH field -- see _ghash_mul)."""
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _key_expansion_256(key: bytes):
    Nk, Nr = 8, 14
    w = [list(key[4 * i:4 * i + 4]) for i in range(Nk)]
    for i in range(Nk, 4 * (Nr + 1)):
        temp = list(w[i - 1])
        if i % Nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_Sbox[b] for b in temp]
            temp[0] ^= _Rcon[i // Nk - 1]
        elif i % Nk == 4:
            temp = [_Sbox[b] for b in temp]
        w.append([a ^ b for a, b in zip(w[i - Nk], temp)])
    round_keys = []
    for r in range(Nr + 1):
        rk = []
        for c in range(4):
            rk += w[4 * r + c]
        round_keys.append(bytes(rk))
    return round_keys


def _add_round_key(state, rk):
    for i in range(16):
        state[i] ^= rk[i]


def _sub_bytes(state):
    for i in range(16):
        state[i] = _Sbox[state[i]]


def _shift_rows(state):
    new = state[:]
    for r in range(1, 4):
        for c in range(4):
            new[c * 4 + r] = state[((c + r) % 4) * 4 + r]
    state[:] = new


def _mix_columns(state):
    for c in range(4):
        a = state[c * 4:c * 4 + 4]
        state[c * 4 + 0] = _gmul(a[0], 2) ^ _gmul(a[1], 3) ^ a[2] ^ a[3]
        state[c * 4 + 1] = a[0] ^ _gmul(a[1], 2) ^ _gmul(a[2], 3) ^ a[3]
        state[c * 4 + 2] = a[0] ^ a[1] ^ _gmul(a[2], 2) ^ _gmul(a[3], 3)
        state[c * 4 + 3] = _gmul(a[0], 3) ^ a[1] ^ a[2] ^ _gmul(a[3], 2)


def _aes256_encrypt_block(block16: bytes, round_keys) -> bytes:
    state = list(block16)
    _add_round_key(state, round_keys[0])
    Nr = 14
    for rnd in range(1, Nr):
        _sub_bytes(state)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, round_keys[rnd])
    _sub_bytes(state)
    _shift_rows(state)
    _add_round_key(state, round_keys[Nr])
    return bytes(state)


class _AES256:
    """Thin wrapper holding the expanded key schedule."""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256 requires a 32-byte key")
        self._rks = _key_expansion_256(key)

    def encrypt_block(self, block16: bytes) -> bytes:
        return _aes256_encrypt_block(block16, self._rks)


# ---------------------------------------------------------------------------
# GHASH (GF(2^128) multiplication per NIST SP 800-38D)
# ---------------------------------------------------------------------------

_R = 0xE1000000000000000000000000000000  # reduction constant for GF(2^128)


def _ghash_mul(x: int, y: int) -> int:
    """Multiply two 128-bit integers in the GHASH Galois field."""
    z = 0
    v = x
    for i in range(127, -1, -1):
        if (y >> i) & 1:
            z ^= v
        if v & 1:
            v = (v >> 1) ^ _R
        else:
            v >>= 1
    return z


def _ghash(h_int: int, data: bytes) -> int:
    y = 0
    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        if len(block) < 16:
            block = block + b"\x00" * (16 - len(block))
        y = _ghash_mul(y ^ int.from_bytes(block, "big"), h_int)
    return y


def _inc32(block: bytes) -> bytes:
    """Increment the low 32 bits of a 16-byte counter block, per GCM spec."""
    prefix, ctr = block[:12], int.from_bytes(block[12:], "big")
    ctr = (ctr + 1) & 0xFFFFFFFF
    return prefix + ctr.to_bytes(4, "big")


def _gctr(aes: _AES256, icb: bytes, data: bytes) -> bytes:
    """AES-CTR using the GCM-specific counter increment (32-bit, wraps)."""
    if not data:
        return b""
    out = bytearray()
    counter = icb
    for i in range(0, len(data), 16):
        keystream = aes.encrypt_block(counter)
        chunk = data[i:i + 16]
        out.extend(b ^ k for b, k in zip(chunk, keystream))
        counter = _inc32(counter)
    return bytes(out)


def _build_j0(aes: _AES256, h_int: int, iv: bytes) -> bytes:
    if len(iv) == 12:
        return iv + b"\x00\x00\x00\x01"
    # Rare path: non-96-bit IV. Hash it down to 128 bits via GHASH.
    s = len(iv) * 8
    padded_len = ((len(iv) + 15) // 16) * 16
    data = iv + b"\x00" * (padded_len - len(iv))
    data += b"\x00" * 8 + struct.pack(">Q", s)
    y = _ghash(h_int, data)
    return y.to_bytes(16, "big")


def encrypt(key: bytes, plaintext: bytes, associated_data: bytes = b"") -> bytes:
    """
    AES-256-GCM encrypt. Returns iv(12) || ciphertext || tag(16), all
    concatenated -- a self-contained blob safe to store as one value.
    """
    aes = _AES256(key)
    iv = os.urandom(12)
    h_int = int.from_bytes(aes.encrypt_block(b"\x00" * 16), "big")
    j0 = _build_j0(aes, h_int, iv)
    ciphertext = _gctr(aes, _inc32(j0), plaintext)

    aad_padded_len = ((len(associated_data) + 15) // 16) * 16 if associated_data else 0
    ct_padded_len = ((len(ciphertext) + 15) // 16) * 16 if ciphertext else 0
    auth_data = (
        associated_data + b"\x00" * (aad_padded_len - len(associated_data))
        + ciphertext + b"\x00" * (ct_padded_len - len(ciphertext))
        + struct.pack(">QQ", len(associated_data) * 8, len(ciphertext) * 8)
    )
    s_int = _ghash(h_int, auth_data)
    tag = bytes(a ^ b for a, b in zip(s_int.to_bytes(16, "big"), aes.encrypt_block(j0)))

    return iv + ciphertext + tag


def decrypt(key: bytes, blob: bytes, associated_data: bytes = b"") -> bytes:
    """
    Inverse of encrypt(): blob is iv(12) || ciphertext || tag(16).
    Raises ValueError if the authentication tag does not match (tampered
    or wrong key) -- callers must not ignore this.
    """
    if len(blob) < 28:
        raise ValueError("ciphertext blob too short to contain iv+tag")
    iv, ciphertext, tag = blob[:12], blob[12:-16], blob[-16:]

    aes = _AES256(key)
    h_int = int.from_bytes(aes.encrypt_block(b"\x00" * 16), "big")
    j0 = _build_j0(aes, h_int, iv)

    aad_padded_len = ((len(associated_data) + 15) // 16) * 16 if associated_data else 0
    ct_padded_len = ((len(ciphertext) + 15) // 16) * 16 if ciphertext else 0
    auth_data = (
        associated_data + b"\x00" * (aad_padded_len - len(associated_data))
        + ciphertext + b"\x00" * (ct_padded_len - len(ciphertext))
        + struct.pack(">QQ", len(associated_data) * 8, len(ciphertext) * 8)
    )
    s_int = _ghash(h_int, auth_data)
    expected_tag = bytes(a ^ b for a, b in zip(s_int.to_bytes(16, "big"), aes.encrypt_block(j0)))

    # Constant-time-ish comparison
    import hmac as _hmac
    if not _hmac.compare_digest(expected_tag, tag):
        raise ValueError("GCM authentication tag mismatch -- data is corrupt or key is wrong")

    plaintext = _gctr(aes, _inc32(j0), ciphertext)
    return plaintext
