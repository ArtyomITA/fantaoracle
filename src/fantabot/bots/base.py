"""Interfaccia comune dei bot al tavolo.

Il motore chiama i bot in due momenti:
- nominate(): tocca a te chiamare un giocatore (obbligatorio, non si salta).
- bid(): un giocatore e' all'asta, decidi se rilanciare.

Ogni risposta porta un `thought`: una riga di motivazione che finisce
nell'event log e alimenta i fumetti del replay.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import Player, TeamState


@dataclass
class NominationDecision:
    player_id: str
    opening_bid: int
    thought: str = ""


@dataclass
class BidDecision:
    amount: int | None   # None = passo; altrimenti offerta totale (>= corrente + incremento)
    thought: str = ""


class Bot:
    name: str = "bot"

    def __init__(self, rng, profile: dict | None = None):
        self.rng = rng
        self.profile = profile or {}

    def start_auction(self, view: "AuctionView") -> None:
        """Hook di inizio asta (pianificazione pre-asta)."""

    def nominate(self, view: "AuctionView") -> NominationDecision:
        raise NotImplementedError

    def bid(self, view: "AuctionView", player: Player, price: int,
            leader: str | None) -> BidDecision:
        raise NotImplementedError

    def on_hammer(self, view: "AuctionView", player: Player, price: int,
                  winner: str) -> None:
        """Hook post-aggiudicazione (per replanning: B ricalcola qui)."""


@dataclass
class AuctionView:
    """Cio' che un bot vede del tavolo (informazione pubblica + il proprio stato)."""
    me: TeamState
    others: list[TeamState]          # stati pubblici degli avversari (budget e rose sono pubblici)
    quotas: dict[str, int]
    budget_total: int
    current_role: str
    pool: dict[str, Player]          # giocatori ancora disponibili (tutti i ruoli)
    sold: list[tuple[str, str, int]]  # (player_id, team_id, prezzo) in ordine cronologico

    def available(self, role: str | None = None) -> list[Player]:
        ps = [p for p in self.pool.values()]
        if role:
            ps = [p for p in ps if p.role == role]
        return ps

    def inflation(self) -> float:
        """Crediti residui in stanza / valore di riferimento residuo."""
        credits_left = self.me.budget + sum(t.budget for t in self.others)
        ref_left = sum(p.ref_price for p in self.pool.values()) * self.budget_total
        return credits_left / ref_left if ref_left > 0 else 1.0
