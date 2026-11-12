"""Optional inference for sufficiently large, paired evaluation experiments."""

from math import comb
from statistics import NormalDist

from pydantic import BaseModel, Field


class ProportionInterval(BaseModel):
    successes: int = Field(ge=0)
    trials: int = Field(ge=1)
    confidence: float = Field(gt=0, lt=1)
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)


class McNemarResult(BaseModel):
    pairs: int = Field(ge=0)
    discordant_left: int = Field(ge=0)
    discordant_right: int = Field(ge=0)
    p_value: float = Field(ge=0, le=1)


def wilson_interval(
    successes: int, trials: int, *, confidence: float = 0.95
) -> ProportionInterval | None:
    """Return a Wilson interval, or None when the denominator is unavailable."""
    if type(successes) is not int or type(trials) is not int:
        raise ValueError("Interval counts must be integers")
    if successes < 0 or trials < 0 or successes > trials:
        raise ValueError("Invalid interval counts")
    if trials == 0:
        return None
    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between 0 and 1")
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    proportion = successes / trials
    denominator = 1 + z**2 / trials
    center = (proportion + z**2 / (2 * trials)) / denominator
    margin = (
        z * ((proportion * (1 - proportion) / trials + z**2 / (4 * trials**2)) ** 0.5) / denominator
    )
    return ProportionInterval(
        successes=successes,
        trials=trials,
        confidence=confidence,
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
    )


def _binomial_probability(total: int, successes: int) -> float:
    return comb(total, successes) / 2**total


def mcnemar_exact(left: list[bool], right: list[bool]) -> McNemarResult:
    """Compare two binary predictions on the same ordered cases."""
    if len(left) != len(right):
        raise ValueError("McNemar inputs must contain the same paired cases")
    discordant_left = sum(a and not b for a, b in zip(left, right, strict=True))
    discordant_right = sum(not a and b for a, b in zip(left, right, strict=True))
    discordant = discordant_left + discordant_right
    if not discordant:
        p_value = 1.0
    else:
        lower_tail = sum(
            _binomial_probability(discordant, k)
            for k in range(0, min(discordant_left, discordant_right) + 1)
        )
        upper_tail = sum(
            _binomial_probability(discordant, k)
            for k in range(max(discordant_left, discordant_right), discordant + 1)
        )
        p_value = min(1.0, 2 * min(lower_tail, upper_tail))
    return McNemarResult(
        pairs=len(left),
        discordant_left=discordant_left,
        discordant_right=discordant_right,
        p_value=p_value,
    )


def holm_adjust(p_values: list[float]) -> list[float]:
    """Apply Holm's step-down correction while preserving input order."""
    if any(not 0 <= value <= 1 for value in p_values):
        raise ValueError("P-values must be between 0 and 1")
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted: list[float] = [0.0] * len(p_values)
    running = 0.0
    for rank, (index, value) in enumerate(ordered):
        running = max(running, min(1.0, (len(p_values) - rank) * value))
        adjusted[index] = running
    return adjusted
