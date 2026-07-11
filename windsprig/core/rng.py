from __future__ import annotations

import hashlib
import random


def derive_stage_seed(base_seed: int, stage_id: str) -> int:
    if not stage_id.strip():
        raise ValueError("stage_id must not be blank")
    payload = f"windsprig:v1:{base_seed}:{stage_id}".encode("utf-8")
    digest = hashlib.blake2s(payload, digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


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
