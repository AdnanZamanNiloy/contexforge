"""Local Risk Score (LRS) and the health summary.

A direct port of ``hotspots``' ``hotspots-core/src/risk.rs``, including its
transforms, default weights and band thresholds.  The point of carrying it over
verbatim is that it is **deterministic and explainable**: every number in the
report can be traced to four integer metrics through a formula that is printed
next to the result.  No model is involved, which is also why the scan finishes
in milliseconds.

The transforms are what make the score comparable across repositories.  Raw
complexity has a long tail, so each component is squashed (logarithmically for
counts, capped for depths) before weighting — a function ten times as complex
does not score ten times as risky.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "RISK_WEIGHTS",
    "LrsWeights",
    "RiskBand",
    "RiskComponents",
    "analyze",
    "band_for",
    "health_from_bands",
]

# Default weights, from the tool's LrsWeights::default().
RISK_WEIGHTS = {"cc": 1.0, "nd": 0.8, "fo": 0.6, "ns": 0.7}

# Band thresholds, from the tool's RiskThresholds::default().
MODERATE_AT = 3.0
HIGH_AT = 6.0
CRITICAL_AT = 9.0

# The maximum LRS the weights and caps permit: every component at its ceiling.
MAX_LRS = RISK_WEIGHTS["cc"] * 6.0 + RISK_WEIGHTS["nd"] * 8.0 + RISK_WEIGHTS["fo"] * 6.0 + RISK_WEIGHTS["ns"] * 6.0


@dataclass(frozen=True)
class LrsWeights:
    cc: float = 1.0
    nd: float = 0.8
    fo: float = 0.6
    ns: float = 0.7


@dataclass(frozen=True)
class RiskComponents:
    r_cc: float
    r_nd: float
    r_fo: float
    r_ns: float


@dataclass(frozen=True)
class RiskBand:
    name: str  # low | moderate | high | critical
    label: str

    @property
    def rank(self) -> int:
        return {"low": 0, "moderate": 1, "high": 2, "critical": 3}[self.name]


_LOW = RiskBand("low", "Low")
_MODERATE = RiskBand("moderate", "Moderate")
_HIGH = RiskBand("high", "High")
_CRITICAL = RiskBand("critical", "Critical")
BANDS = (_LOW, _MODERATE, _HIGH, _CRITICAL)


def band_for(lrs: float) -> RiskBand:
    """Classify an LRS. Thresholds match the tool's defaults."""
    if lrs < MODERATE_AT:
        return _LOW
    if lrs < HIGH_AT:
        return _MODERATE
    if lrs < CRITICAL_AT:
        return _HIGH
    return _CRITICAL


def analyze(metrics, weights: LrsWeights | None = None) -> tuple[RiskComponents, float, RiskBand]:
    """Turn raw metrics into transformed components, an LRS and a band.

    The transforms, from the tool's ``calculate_risk_components``:

    * ``R_cc = min(log2(CC + 1), 6)``
    * ``R_nd = min(ND, 8)``
    * ``R_fo = min(log2(FO + 1), 6)``
    * ``R_ns = min(NS, 6)``
    """
    w = weights or LrsWeights()
    components = RiskComponents(
        r_cc=min(math.log2(metrics.cc + 1), 6.0),
        r_nd=float(min(metrics.nd, 8)),
        r_fo=min(math.log2(metrics.fo + 1), 6.0),
        r_ns=float(min(metrics.ns, 6)),
    )
    lrs = w.cc * components.r_cc + w.nd * components.r_nd + w.fo * components.r_fo + w.ns * components.r_ns
    return components, lrs, band_for(lrs)


def health_from_bands(counts: dict[str, int], total: int) -> int:
    """A 0-100 health figure derived from how many symbols fall in each band.

    Deliberately a *summary of the one risk axis*, not a blend of independent
    signals.  The tool is explicit that its axes (risk, churn, coupling,
    ownership) are measured with low correlation and must not be composited —
    a single number implying otherwise would be misleading.  So this reports
    only structural risk, and the response says so in as many words.

    The curve is a weighted penalty per band, then scaled so an all-low
    codebase scores 100 and the worst observed mix approaches 0.
    """
    if total <= 0:
        return 100
    penalty = (
        counts.get("low", 0) * 0.0
        + counts.get("moderate", 0) * 0.35
        + counts.get("high", 0) * 0.7
        + counts.get("critical", 0) * 1.0
    )
    share = penalty / total
    return max(0, min(100, round(100 - share * 100)))
