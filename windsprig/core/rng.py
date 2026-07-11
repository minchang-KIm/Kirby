from __future__ import annotations

import hashlib
import random


class DeterministicRng:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._rng = random.Random(seed)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def random(self) -> float:
        return self._rng.random()

    def choice(self, seq: list[object]) -> object:
        return self._rng.choice(seq)

    def state_hash(self) -> str:
        return hashlib.sha256(repr(self._rng.getstate()).encode("utf-8")).hexdigest()[:16]
