"""Modelli dati condivisi: giocatori, squadre al tavolo, eventi d'asta."""
from __future__ import annotations

from dataclasses import dataclass, field

ROLES = ("P", "D", "C", "A")


@dataclass(frozen=True)
class Player:
    player_id: str
    name: str
    role: str            # P/D/C/A
    team: str            # squadra Serie A
    # riferimenti prezzo/valore usati dai bot (riempiti dai loader di Fase 0b)
    ref_price: float = 0.0       # prezzo di riferimento in % budget (0-1)
    ref_price_sd: float = 0.0    # spread osservato tra aste reali (% budget)
    exp_points: float = 0.0      # fantapunti attesi stagione (modello valore)


@dataclass
class TeamState:
    team_id: str
    bot_name: str
    budget: int
    roster: dict[str, list[tuple[str, int]]] = field(
        default_factory=lambda: {r: [] for r in ROLES}
    )  # ruolo -> [(player_id, prezzo)]

    def slots_left(self, quotas: dict[str, int], role: str | None = None) -> int:
        if role is not None:
            return quotas[role] - len(self.roster[role])
        return sum(quotas[r] - len(self.roster[r]) for r in ROLES)

    def max_bid(self, quotas: dict[str, int], min_price: int = 1) -> int:
        """Offerta massima: deve restare 1 credito per ogni altro slot vuoto."""
        empty_after = self.slots_left(quotas) - 1
        return self.budget - empty_after * min_price

    def can_bid(self, quotas: dict[str, int], role: str, amount: int) -> bool:
        return (
            self.slots_left(quotas, role) > 0
            and amount <= self.max_bid(quotas)
        )


@dataclass
class AuctionEvent:
    """Riga dell'event log JSONL. `kind` in:
    auction_start, phase_start, nomination, bid, hammer, auction_end."""
    seq: int
    kind: str
    payload: dict

    def to_dict(self) -> dict:
        return {"seq": self.seq, "kind": self.kind, **self.payload}
