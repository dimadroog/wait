"""H4: chunking timesteps для periodic FCEUX recycle (segmented learn)."""
from __future__ import annotations


def iter_learn_chunks(remaining: int, recycle_every_timesteps: int) -> list[int]:
    """Разбить remaining env-steps на чанки; recycle_every<=0 → один чанк."""
    left = max(int(remaining), 0)
    if left <= 0:
        return []
    every = int(recycle_every_timesteps)
    if every <= 0:
        return [left]
    chunks: list[int] = []
    while left > 0:
        chunk = min(every, left)
        chunks.append(chunk)
        left -= chunk
    return chunks
