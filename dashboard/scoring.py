from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.models import ListingScore

DEFAULT_WEIGHTS: dict[str, float] = {
    "price_pct": 0.25,
    "price_m2_pct": 0.30,
    "condition_price_pct": 0.10,
    "energy_score": 0.05,
    "building_type_score": 0.05,
    "floor_elevator_penalty": 0.05,
    "drop_recency": 0.05,
    "market_delta": 0.10,
    "land_pct": 0.05,
}


def _normalise(key: str, value: float) -> float:
    match key:
        case "price_pct" | "price_m2_pct" | "condition_price_pct" | "land_pct":
            return 100.0 - value
        case "energy_score" | "building_type_score":
            return value / 5.0 * 100.0
        case "floor_elevator_penalty":
            return (value + 20.0) / 20.0 * 100.0
        case "drop_recency":
            return max(0.0, 100.0 - value / 90.0 * 100.0)
        case "market_delta":
            clamped = max(-30.0, min(30.0, value))
            return (30.0 - clamped) / 60.0 * 100.0
        case _:
            return 50.0


def compute_live_score(
    score: Optional["ListingScore"],
    weights: dict[str, float],
) -> Optional[float]:
    if score is None:
        return None
    total_weight = sum(weights.values())
    if total_weight == 0:
        return None

    signal_map = {
        "price_pct": score.price_percentile,
        "price_m2_pct": score.price_per_m2_percentile,
        "condition_price_pct": score.condition_price_pct,
        "energy_score": score.energy_score,
        "building_type_score": score.building_type_score,
        "floor_elevator_penalty": score.floor_elevator_penalty,
        "drop_recency": score.drop_recency_days,
        "market_delta": score.market_delta_pct,
        "land_pct": score.combined_area_price_pct,
    }

    total = sum(
        weights.get(k, 0.0) * (_normalise(k, v) if v is not None else 50.0)
        for k, v in signal_map.items()
    )
    return round(total / total_weight, 1)
