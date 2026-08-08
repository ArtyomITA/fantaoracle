"""Bot A: il ragioniere. Lista prezzi VORP precalcolata, max bid rigidi,
allocazione budget da guida, zero psicologia.

In Fase 2 la lista arriva dal calcolo VORP sui dati pre-asta; qui il bot
accetta una price list esterna (player_id -> prezzo equo in crediti).
Variante `flessibile`: tolleranza +10% sui propri target.
"""
from __future__ import annotations

from .base import AuctionView, BidDecision, Bot, NominationDecision
from ..models import Player


class ABot(Bot):
    def __init__(self, rng, price_list: dict[str, float] | None = None,
                 flexible: bool = False):
        super().__init__(rng)
        self.name = "A-flessibile" if flexible else "A-rigido"
        self.tol = 1.10 if flexible else 1.0
        self.price_list = price_list or {}

    def start_auction(self, view: AuctionView):
        if not self.price_list:
            # fallback smoke-test: usa il riferimento come lista
            self.price_list = {pid: max(1.0, p.ref_price * view.budget_total)
                               for pid, p in view.pool.items()}

    def _max_for(self, player: Player, view: AuctionView | None = None) -> float:
        cap = self.price_list.get(player.player_id, 1.0) * self.tol
        if self.tol > 1.0 and view is not None:
            # variante flessibile: applica il fattore inflazione alla lista
            # (metodo FantasyPros); il rigido resta fedele alla lista stampata
            cap *= min(1.8, max(0.85, view.inflation()))
        return cap

    def bid(self, view: AuctionView, player: Player, price: int, leader) -> BidDecision:
        cap = self._max_for(player, view)
        nxt = price + 1
        if nxt <= cap:
            return BidDecision(nxt, f"lista dice {cap:.0f}")
        return BidDecision(None, f"oltre lista ({cap:.0f}), passo")

    def nominate(self, view: AuctionView) -> NominationDecision:
        role = view.current_role
        avail = view.available(role)
        # chiama il miglior valore secondo lista (semplice e prevedibile)
        pick = max(avail, key=lambda p: self.price_list.get(p.player_id, 0))
        opening = max(1, int(self._max_for(pick) * 0.3))
        opening = min(opening, view.me.max_bid(view.quotas))
        return NominationDecision(pick.player_id, opening, f"da lista: {pick.name}")
