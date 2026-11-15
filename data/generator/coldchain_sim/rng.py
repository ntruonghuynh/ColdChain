"""Deterministic seed derivation.

Every random stream is derived from named parts with SHA-256, so

* the same (seed, config) always gives the same output (NFR-03);
* each journey has its own independent stream: a journey's data depends only on
  its own seed, scenario, ambient profile and the configuration, not on other journeys;
* adding a draw to one stream (for example the sensor model) does not shift another
  stream (for example the physics).

``random.Random`` (Mersenne Twister) is specified and stable across platforms and
Python versions for ``random()``, ``uniform`` and ``gauss``.
"""

import hashlib
import random


def derive_seed(*parts: object) -> int:
    """64-bit integer seed from named parts, e.g. ``derive_seed("coldchain-sim", 11, "journey", 7)``."""
    text = "|".join(str(p) for p in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def make_rng(*parts: object) -> random.Random:
    return random.Random(derive_seed(*parts))
