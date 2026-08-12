"""Flag token generation.

The paper hides a short token like ``flag{a3b1c9...}``. Tokens are random, so the
mechanical "flag must not appear as plaintext on disk" check is meaningful and a
recovered string can be verified by exact match.
"""

from __future__ import annotations

import string
from random import Random

_HEX = "0123456789abcdef"


def make_token(rng: Random, nybbles: int = 16) -> str:
    body = "".join(rng.choice(_HEX) for _ in range(nybbles))
    return f"flag{{{body}}}"


def is_token(s: str) -> bool:
    s = s.strip()
    if not (s.startswith("flag{") and s.endswith("}")):
        return False
    inner = s[5:-1]
    return len(inner) > 0 and all(c in string.hexdigits for c in inner)
