"""比例与率差的区间估计，只用标准库。

- Wilson 得分区间用于单组独立完成率；
- Newcombe 区间用于两臂率差（不作连续性校正）。
"""
from __future__ import annotations

from statistics import NormalDist


def _z(confidence: float) -> float:
    return NormalDist().inv_cdf(0.5 + confidence / 2.0)


def wilson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """k/n 的 Wilson 得分区间；n 为 0 时返回 (nan, nan)。"""
    if n <= 0:
        return (float("nan"), float("nan"))
    z = _z(confidence)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * ((p * (1.0 - p) / n + z * z / (4.0 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe(
    k1: int, n1: int, k2: int, n2: int, confidence: float = 0.95
) -> tuple[float, float]:
    """率差 p1 - p2 的 Newcombe 区间。"""
    lo1, hi1 = wilson(k1, n1, confidence)
    lo2, hi2 = wilson(k2, n2, confidence)
    return (lo1 - hi2, hi1 - lo2)
