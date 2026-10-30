"""Independent, named random streams derived from one seed."""
from __future__ import annotations

import numpy as np

STREAM_NAMES = ("masters", "dynamics", "post", "anomalies")  # append only: earlier streams never shift


def streams(seed: int) -> dict[str, np.random.Generator]:
    children = np.random.SeedSequence(seed).spawn(len(STREAM_NAMES))
    return {name: np.random.default_rng(ss) for name, ss in zip(STREAM_NAMES, children)}