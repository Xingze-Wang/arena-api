from arena_api.config import K_FACTOR

def expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

def update(ra: float, rb: float, winner: str) -> tuple[float, float]:
    ea = expected(ra, rb)
    eb = 1.0 - ea
    if winner == "a":
        sa, sb = 1.0, 0.0
    elif winner == "b":
        sa, sb = 0.0, 1.0
    else:
        sa, sb = 0.5, 0.5
    return ra + K_FACTOR * (sa - ea), rb + K_FACTOR * (sb - eb)
