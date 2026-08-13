from __future__ import annotations

import os
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_lock = threading.Lock()
_last_millis = -1
_last_random = 0


def _encode(value: int, length: int) -> str:
    output = ["0"] * length
    for index in range(length - 1, -1, -1):
        output[index] = _ALPHABET[value & 31]
        value >>= 5
    return "".join(output)


def monotonic_ulid() -> str:
    global _last_millis, _last_random
    with _lock:
        now = int(time.time_ns() // 1_000_000)
        if now == _last_millis:
            _last_random = (_last_random + 1) & ((1 << 80) - 1)
            if _last_random == 0:
                while now <= _last_millis:
                    now = int(time.time_ns() // 1_000_000)
        else:
            _last_random = int.from_bytes(os.urandom(10), "big")
        _last_millis = now
        return _encode(now, 10) + _encode(_last_random, 16)


def principle_id(area: str) -> str:
    normalized = area.strip().lower()
    if not normalized or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in normalized
    ):
        raise ValueError("area must contain only lowercase letters, digits, and hyphens")
    return f"prn:{normalized}:{monotonic_ulid()}"


def candidate_id() -> str:
    return f"cand:{monotonic_ulid()}"


def event_id(prefix: str = "evt") -> str:
    return f"{prefix}:{monotonic_ulid()}"
