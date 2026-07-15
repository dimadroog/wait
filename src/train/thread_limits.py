"""Лимиты CPU-потоков при параллельном train (FAIL_REPORT R3.1)."""
from __future__ import annotations

import os

import torch

PARALLEL_ENV_THREAD_CAP = 6
MAX_THREADS_HIGH_ENV = 2
_BLAS_ENV_VARS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def configure_train_threads(*, n_envs: int, threads: int) -> dict[str, int]:
    """Ограничить torch/BLAS при n_envs≥6 — снижает OpenBLAS OOM на фоне FCEUX workers."""
    effective = min(threads, MAX_THREADS_HIGH_ENV) if n_envs >= PARALLEL_ENV_THREAD_CAP else threads
    if effective != threads:
        print(
            f"train threads capped: {threads} -> {effective} "
            f"(n_envs={n_envs} >= {PARALLEL_ENV_THREAD_CAP})"
        )
    for var in _BLAS_ENV_VARS:
        os.environ[var] = str(effective)
    torch.set_num_threads(effective)
    return {
        "torch_threads": effective,
        "openblas_threads": effective,
        "n_envs": n_envs,
        "requested_threads": threads,
    }
