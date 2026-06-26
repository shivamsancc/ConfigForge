"""
Pure-Python AES-256-GCM. Zero external dependencies.

Output format for encrypt(): iv(12 bytes) || ciphertext || tag(16 bytes),
all concatenated and base64-encoded by the caller (storage.py).

This is a from-scratch implementation: AES block cipher (S-box, key
schedule, ShiftRows/MixColumns), GHASH over GF(2^128), and CTR mode for
the actual encryption. It is NOT constant-time and should not be treated
as hardened against timing side-channels — it exists so this project has
zero pip dependencies, not as a general-purpose crypto library.
"""
import os
import struct

# ---------------------------------------------------------------------------
# AES S-box and inverse S-box
# ---------------------------------------------------------------------------
_SBOX = [
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

_RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36,0x6C,0xD8,0xAB,0x4D]


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11B
    return a & 0xFF


def _gmul(a, b):
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
    nk = 8  # 256-bit key = 8 words
    nr = 14  # rounds
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    # Group into round keys (each round key = 4 words = 16 bytes)
    round_keys = []
    for r in range(nr + 1):
        rk = []
        for c in range(4):
            rk.extend(w[r * 4 + c])
        round_keys.append(bytes(rk))
    return round_keys


def _add_round_key(state, rk):
    return bytes(s ^ k for s, k in zip(state, rk))


def _sub_bytes(state):
    return bytes(_SBOX[b] for b in state)


def _shift_rows(state):
    # state is column-major 4x4: state[r + 4*c]
    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[r + 4 * c] = state[r + 4 * ((c + r) % 4)]
    return bytes(out)


def _mix_columns(state):
    out = bytearray(16)
    for c in range(4):
        col = state[4 * c:4 * c + 4]
        out[4 * c + 0] = _gmul(col[0], 2) ^ _gmul(col[1], 3) ^ col[2] ^ col[3]
        out[4 * c + 1] = col[0] ^ _gmul(col[1], 2) ^ _gmul(col[2], 3) ^ col[3]
        out[4 * c + 2] = col[0] ^ col[1] ^ _gmul(col[2], 2) ^ _gmul(col[3], 3)
        out[4 * c + 3] = _gmul(col[0], 3) ^ col[1] ^ col[2] ^ _gmul(col[3], 2)
    return bytes(out)


def _aes256_encrypt_block(block: bytes, round_keys) -> bytes:
    nr = 14
    state = _add_round_key(block, round_keys[0])
    for rnd in range(1, nr):
        state = _sub_bytes(state)
        state = _shift_rows(state)
        state = _mix_columns(state)
        state = _add_round_key(state, round_keys[rnd])
    state = _sub_bytes(state)
    state = _shift_rows(state)
    state = _add_round_key(state, round_keys[nr])
    return state


class _AES256:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256 key must be 32 bytes")
        self._round_keys = _key_expansion_256(key)

    def encrypt_block(self, block: bytes) -> bytes:
        return _aes256_encrypt_block(block, self._round_keys)


# ---------------------------------------------------------------------------
# GHASH over GF(2^128) for GCM authentication
# ---------------------------------------------------------------------------
_R = 0xE1000000000000000000000000000000


def _gf128_mul(x: int, y: int) -> int:
    z = 0
    for i in range(127, -1, -1):
        if (x >> i) & 1:
            z ^= y
        if y & 1:
            y = (y >> 1) ^ _R
        else:
            y >>= 1
    return z & ((1 << 128) - 1)


def _ghash(h: int, data: bytes) -> int:
    y = 0
    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        if len(block) < 16:
            block = block + b"\x00" * (16 - len(block))
        y ^= int.from_bytes(block, "big")
        y = _gf128_mul(y, h)
    return y


def _ghash_full(h: int, aad: bytes, ciphertext: bytes) -> bytes:
    def pad16(b):
        rem = len(b) % 16
        return b if rem == 0 else b + b"\x00" * (16 - rem)

    data = pad16(aad) + pad16(ciphertext)
    data += struct.pack(">QQ", len(aad) * 8, len(ciphertext) * 8)
    y = _ghash(h, data)
    return y.to_bytes(16, "big")


def _inc32(block: bytes) -> bytes:
    counter = int.from_bytes(block[-4:], "big")
    counter = (counter + 1) & 0xFFFFFFFF
    return block[:-4] + counter.to_bytes(4, "big")


def _gctr(aes: _AES256, icb: bytes, data: bytes) -> bytes:
    out = bytearray()
    counter = icb
    for i in range(0, len(data), 16):
        keystream = aes.encrypt_block(counter)
        chunk = data[i:i + 16]
        out.extend(b ^ k for b, k in zip(chunk, keystream))
        counter = _inc32(counter)
    return bytes(out)


def encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """Returns iv(12) || ciphertext || tag(16)."""
    aes = _AES256(key)
    iv = os.urandom(12)
    h = int.from_bytes(aes.encrypt_block(b"\x00" * 16), "big")
    j0 = iv + b"\x00\x00\x00\x01"
    # Ciphertext encryption starts at J0+1; J0 itself is reserved for the
    # auth tag mask below (GCM spec, NIST SP 800-38D section 7.1).
    ciphertext = _gctr(aes, _inc32(j0), plaintext)
    s = _ghash_full(h, aad, ciphertext)
    auth_keystream = aes.encrypt_block(j0)
    tag = bytes(a ^ b for a, b in zip(s, auth_keystream))
    return iv + ciphertext + tag


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    """Input: iv(12) || ciphertext || tag(16). Raises ValueError on tamper."""
    if len(blob) < 28:
        raise ValueError("ciphertext too short")
    iv = blob[:12]
    tag = blob[-16:]
    ciphertext = blob[12:-16]
    aes = _AES256(key)
    h = int.from_bytes(aes.encrypt_block(b"\x00" * 16), "big")
    j0 = iv + b"\x00\x00\x00\x01"
    s = _ghash_full(h, aad, ciphertext)
    auth_keystream = aes.encrypt_block(j0)
    expected_tag = bytes(a ^ b for a, b in zip(s, auth_keystream))
    if not _consteq(expected_tag, tag):
        raise ValueError("authentication tag mismatch (tampered or wrong key)")
    # Decryption (like encryption) starts at J0+1.
    return _gctr(aes, _inc32(j0), ciphertext)


def _consteq(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return False
    r = 0
    for x, y in zip(a, b):
        r |= x ^ y
    return r == 0
