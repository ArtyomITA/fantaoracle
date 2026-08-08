"""Bot B: la pipeline. Predizioni prezzo distribuzionali + MILP + replanning.

Il bot riceve `predictions`: player_id -> {"q10","q50","q90","value"}
(quantili prezzo in crediti + punti attesi) calcolate OFFLINE dai modelli di
Fase 1 con dati pre-asta. La policy al tavolo:

- pre-asta: MILP su q50 -> rosa target + max bid;
- misura l'inflazione REALE confrontando i prezzi battuti con le proprie q50
  e corregge i max bid;
- rilancia sui target fino al max bid; coglie i bargain sotto q10;
- nomination: chiama i pezzi grossi che NON vuole (drena i budget altrui);
- replan MILP dopo ogni evento rilevante (target perso, proprio acquisto,
  oppure ogni K martelletti).
"""
from __future__ import annotations

from .base import AuctionView, BidDecision, Bot, NominationDecision
from ..models import Player
from ..optimizer import STARTER_SLOTS, greedy_roster, optimize_roster


class BBot(Bot):
    name = "B"

    def __init__(self, rng, predictions: dict[str, dict], replan_every: int = 10):
        super().__init__(rng)
        self.pred = predictions
        self.replan_every = replan_every
        self.targets: set[str] = set()
        self.starter_targets: set[str] = set()
        self._role_of: dict[str, str] = {}
        self._best_alt_value: dict[str, float] = {}
        self.hammers_since_replan = 0
        self.infl_num = 0.0   # somma prezzi battuti (sui giocatori con q50 > 3)
        self.infl_den = 0.0   # somma q50 corrispondenti

    # ---------- stime ----------
    def _q(self, pid: str, k: str, default: float = 1.0) -> float:
        return self.pred.get(pid, {}).get(k, default)

    def market_heat(self) -> float:
        """Prezzi reali / miei q50: >1 il tavolo paga sopra le mie stime.
        Bound larghi (fix indagine: nel 2024-25 il mercato pagava 0.36x q50
        e il floor 0.8 teneva i cap troppo alti; nel 2025-26 la coda calda
        sfondava il tetto)."""
        if self.infl_den < 30:
            return 1.0
        return max(0.5, min(1.8, self.infl_num / self.infl_den))

    # valore minimo (punti attesi) per giustificare piu' di 5 crediti:
    # fix anti-zavorra dall'indagine (Bailey/Lukaku 2025-26)
    MIN_VALUE_OVER_5CR = 130.0

    def _dropoff_credits(self, pid: str) -> float:
        """Prezzo-ombra approssimato: quanto vale il giocatore PER LA MIA
        rosa = drop-off di valore verso la migliore alternativa dello stesso
        ruolo fuori piano, convertito in crediti col tasso della fascia."""
        alt = self._best_alt_value.get(self._role_of.get(pid, ""), 0.0)
        gap = max(0.0, self._q(pid, "value", 0.0) - alt)
        # tasso crediti/punto stimato dalla propria lista: q50 / value
        v = self._q(pid, "value", 0.0)
        rate = (self._q(pid, "q50") / v) if v > 0 else 0.05
        return gap * rate

    def _max_bid_for(self, pid: str) -> float:
        heat = self.market_heat()
        if pid in self.starter_targets:
            # base q90, ampliata dal prezzo-ombra se il drop-off e' grande
            # (un unicum merita oltre q90; un sostituibile no)
            cap = self._q(pid, "q90") + 0.5 * self._dropoff_credits(pid)
            return cap * heat
        return max(self._q(pid, "q50") * 1.10, 2.0) * heat

    # ---------- pianificazione ----------
    def start_auction(self, view: AuctionView):
        self._replan(view)

    def _replan(self, view: AuctionView):
        self.hammers_since_replan = 0
        heat = self.market_heat()
        candidates = dict(view.pool)
        quotas_left = {r: view.quotas[r] - len(view.me.roster[r])
                       for r in view.quotas}
        prices = {pid: max(1.0, self._q(pid, "q50") * heat) for pid in candidates}
        values = {pid: self._q(pid, "value", 0.0) for pid in candidates}
        # quanti slot da titolare ho gia' coperto: acquisti con q50 "da titolare"
        starters_owned = {}
        for r, ids in view.me.roster.items():
            n = sum(1 for pid, paid in ids if self._q(pid, "q50") >= 8 or paid >= 8)
            starters_owned[r] = min(n, STARTER_SLOTS[r])
        sol = optimize_roster(candidates, prices, values, quotas_left,
                              view.me.budget, starters_owned=starters_owned,
                              time_limit=5)
        if sol is None:
            sol = greedy_roster(candidates, prices, values, quotas_left,
                                view.me.budget)
            sol["starters"] = set()
        self.targets = {pid for ids in sol["roster"].values() for pid in ids}
        self.starter_targets = set(sol.get("starters") or set())
        # per il prezzo-ombra: miglior valore di ruolo FUORI piano
        self._role_of = {pid: p.role for pid, p in view.pool.items()}
        self._best_alt_value = {}
        for r in quotas_left:
            alts = [self._q(pid, "value", 0.0) for pid, p in view.pool.items()
                    if p.role == r and pid not in self.targets]
            self._best_alt_value[r] = max(alts) if alts else 0.0

    # ---------- comportamento ----------
    def bid(self, view: AuctionView, player: Player, price: int, leader) -> BidDecision:
        pid = player.player_id
        nxt = price + 1
        # guardia anti-zavorra: mai oltre 5 crediti per un valore modesto
        # (fix indagine 2025-26: Lukaku/Bailey comprati contro il modello)
        if nxt > 5 and self._q(pid, "value", 0.0) < self.MIN_VALUE_OVER_5CR:
            return BidDecision(None, "valore basso, non oltre 5")
        if pid in self.targets:
            cap = self._max_bid_for(pid)
            if nxt <= cap:
                return BidDecision(nxt, f"target: q50 {self._q(pid,'q50'):.0f}, "
                                        f"mi spingo a {cap:.0f}")
            return BidDecision(None, f"target perso, oltre {cap:.0f}")
        # bargain: sotto il quantile basso RISCALATO sul mercato reale
        # (fix indagine: q10 gonfiati compravano junk nel 2025-26)
        bargain_cap = min(self._q(pid, "q10"), self._q(pid, "q50") * 0.6) \
            * self.market_heat() * 0.9
        if (view.me.slots_left(view.quotas, player.role) > 0
                and nxt <= bargain_cap
                and self._q(pid, "value", 0.0) >= self.MIN_VALUE_OVER_5CR * 0.7):
            return BidDecision(nxt, f"bargain vero (cap {bargain_cap:.0f})")
        return BidDecision(None, "non in piano")

    def nominate(self, view: AuctionView) -> NominationDecision:
        role = view.current_role
        avail = view.available(role)
        # pezzi grossi che non voglio: li chiamo presto per drenare budget
        non_targets = sorted((p for p in avail if p.player_id not in self.targets),
                             key=lambda p: -self._q(p.player_id, "q50"))
        if non_targets and self._q(non_targets[0].player_id, "q50") > 15:
            p = non_targets[0]
            return NominationDecision(p.player_id, 1,
                                      f"chiamo {p.name}: fatevi male voi")
        # altrimenti un mio riempitivo economico, apertura 1
        own = sorted((p for p in avail if p.player_id in self.targets),
                     key=lambda p: self._q(p.player_id, "q50"))
        p = own[0] if own else avail[0]
        return NominationDecision(p.player_id, 1, f"chiamo {p.name} basso")

    def on_hammer(self, view: AuctionView, player: Player, price: int, winner):
        pid = player.player_id
        q50 = self._q(pid, "q50")
        if q50 > 3:
            self.infl_num += price
            self.infl_den += q50
        self.hammers_since_replan += 1
        relevant = (winner == view.me.team_id
                    or (pid in self.targets and winner != view.me.team_id)
                    or self.hammers_since_replan >= self.replan_every)
        if relevant:
            self._replan(view)
