"""Deterministic event budget calculator. The LLM never does this math (unchanged from the original project)."""
from decimal import Decimal, ROUND_HALF_UP

VENUES = {
    "seminar_hall": {"label": "Seminar Hall", "capacity": 100, "cost": Decimal("3000")},
    "auditorium": {"label": "Auditorium", "capacity": 300, "cost": Decimal("8000")},
}
REFRESHMENT_RATE = Decimal("80")
KIT_RATE = Decimal("120")
CONTINGENCY_RATE = Decimal("0.10")
APPROVAL_LIMIT = Decimal("20000")


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _error(message: str) -> dict:
    return {"error": message}


def estimate_event_budget(venue, participants, refreshments, participation_kits) -> dict:
    """Return the 7 budget fields, or {"error": "<message>"} for invalid input."""
    if venue is None or participants is None or refreshments is None or participation_kits is None:
        return _error("Missing input: venue, participants, refreshments and participation_kits are all required.")

    if not isinstance(venue, str) or venue.strip().lower() not in VENUES:
        return _error("Invalid venue. Choose 'seminar_hall' or 'auditorium'.")
    info = VENUES[venue.strip().lower()]

    # bool is a subclass of int in Python, so reject it explicitly
    if isinstance(participants, bool) or not isinstance(participants, int):
        return _error("Participants must be a whole number (no decimals or text).")
    if participants <= 0:
        return _error("Participants must be a positive whole number greater than zero.")
    if participants > info["capacity"]:
        return _error(
            f"The {info['label']} holds at most {info['capacity']} participants. "
            f"{participants} exceeds its capacity. Reduce the count or choose a larger venue."
        )

    if not isinstance(refreshments, bool) or not isinstance(participation_kits, bool):
        return _error("Refreshments and participation kits must each be True or False.")

    venue_cost = info["cost"]
    refreshment_cost = REFRESHMENT_RATE * participants if refreshments else Decimal("0")
    kit_cost = KIT_RATE * participants if participation_kits else Decimal("0")
    subtotal = venue_cost + refreshment_cost + kit_cost
    contingency = subtotal * CONTINGENCY_RATE
    total = subtotal + contingency
    approver = "Faculty Coordinator" if total <= APPROVAL_LIMIT else "Principal"

    return {
        "venue_cost": _money(venue_cost),
        "refreshment_cost": _money(refreshment_cost),
        "kit_cost": _money(kit_cost),
        "subtotal": _money(subtotal),
        "contingency": _money(contingency),
        "total": _money(total),
        "approver": approver,
    }
