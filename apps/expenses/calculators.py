"""Pure expense split helpers. Amounts are integer paise."""
from decimal import Decimal, ROUND_DOWN

def split_equally(total_paise: int, participant_ids: list[str]) -> dict[str, int]:
    if total_paise <= 0:
        raise ValueError("total_paise must be greater than zero")
    if not participant_ids:
        raise ValueError("At least one participant is required")
    base, remainder = divmod(total_paise, len(participant_ids))
    return {uid: base + (1 if i < remainder else 0) for i, uid in enumerate(participant_ids)}

def split_by_percentage(total_paise: int, percentages: dict[str, Decimal]) -> dict[str, int]:
    if total_paise <= 0 or not percentages:
        raise ValueError("A positive total and participants are required")
    if any(p < 0 for p in percentages.values()) or sum(percentages.values(), Decimal("0")) != Decimal("100"):
        raise ValueError("Percentages must be non-negative and total 100")
    result, fractions = {}, []
    for uid, percent in percentages.items():
        exact = Decimal(total_paise) * percent / Decimal("100")
        base = int(exact.to_integral_value(rounding=ROUND_DOWN))
        result[uid] = base
        fractions.append((exact - base, uid))
    remainder = total_paise - sum(result.values())
    for _, uid in sorted(fractions, reverse=True)[:remainder]:
        result[uid] += 1
    return result

def split_custom(total_paise: int, amounts: dict[str, int]) -> dict[str, int]:
    if not amounts or any(v < 0 for v in amounts.values()):
        raise ValueError("Custom split amounts must be non-negative")
    if sum(amounts.values()) != total_paise:
        raise ValueError("Custom split amounts must equal the total")
    return amounts
