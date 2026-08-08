"""Local extrema helpers — avoids a hard scipy dependency in deploy."""

from __future__ import annotations

import numpy as np


def argrelextrema(data: np.ndarray, comparator, order: int = 5) -> np.ndarray:
    """
    Indices where `data` is a local extremum vs `order` neighbours on each side.

    Mirrors scipy.signal.argrelextrema for the comparator+order usage in VCP detection.
    """
    if order < 1:
        raise ValueError("order must be >= 1")
    n = len(data)
    if n < 2 * order + 1:
        return np.array([], dtype=int)

    hits: list[int] = []
    for i in range(order, n - order):
        window_left = data[i - order : i]
        window_right = data[i + 1 : i + order + 1]
        centre = data[i]
        if np.all(comparator(centre, window_left)) and np.all(comparator(centre, window_right)):
            hits.append(i)
    return np.asarray(hits, dtype=int)
