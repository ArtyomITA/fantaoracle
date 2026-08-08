"""Bot C: avversari umani-realistici guidati da profilo.

Valutazione privata = ref_price (quota % budget) x rumore lognormale
x moltiplicatori di profilo; la disciplina di budget per reparto e' morbida
(gli umani sforano). I quirk riproducono i pattern documentati nelle guide:
tifoso, panic buyer, ancorato, enforcer, tirchio, stars&scrubs, semitop.

La sigma del rumore andra' calibrata in Fase 2 sullo spread reale per
giocatore misurato dalle aste GruppoEsperti.
"""
from __future__ import annotations

import math

from .base import AuctionView, BidDecision, Bot, NominationDecision
from ..models import Player

# allocazione budget di reparto di partenza (consenso guide, lega 10 squadre;
# +3pp verso l'attacco dal fix realismo: le sim sotto-spendevano l'attacco)
BASE_ALLOC = {"P": 0.07, "D": 0.13, "C": 0.235, "A": 0.565}

# tetto umano sul singolo giocatore: nelle 16 aste reali estive 10x500 il piu'
# pagato sta a 0.357 del budget (max osservato 0.424); i profili aggressivi
# senza tetto compravano i top a +25% del reale
TOP_CAP_RANGE = (0.36, 0.42)

PROFILES = {
    "stars_scrubs": dict(top_mult=1.35, mid_mult=0.55, scrub_mult=0.25, sigma=0.30),
    "semitop":      dict(top_mult=0.70, mid_mult=1.20, scrub_mult=0.80, sigma=0.22),
    "tifoso":       dict(team_bias=1.30, sigma=0.28),
    "ancorato":     dict(anchor_w=0.55, sigma=0.20),
    "panic":        dict(panic_step=0.12, panic_cap=1.6, sigma=0.30),
    "tirchio":      dict(value_mult=0.90, sigma=0.20),
    "enforcer":     dict(enforce_p=0.25, enforce_margin=0.82, sigma=0.25),
    "medio":        dict(sigma=0.25),
    # umano informato: non si fida solo del "prezzo di listino" della stanza,
    # lo mescola con la propria stima da fantamedia (hint VORP) — e' quello
    # che fanno gli amici bravi con la guida asta in mano
    "informato":    dict(sigma=0.20, blend_w=0.45),
}


class CBot(Bot):
    def __init__(self, rng, profile_name: str = "medio", fav_team: str | None = None,
                 hint_prices: dict[str, float] | None = None):
        super().__init__(rng, PROFILES[profile_name])
        self.name = f"C-{profile_name}"
        self.profile_name = profile_name
        self.fav_team = fav_team
        self.hint_prices = hint_prices or {}
        self.values: dict[str, float] = {}   # player_id -> valutazione privata in crediti
        self.lost_targets = 0
        self.alloc = {}

    # ---------- pianificazione ----------
    def start_auction(self, view: AuctionView):
        b = view.budget_total
        jitter = {r: max(0.02, a * self.rng.lognormvariate(0, 0.15))
                  for r, a in BASE_ALLOC.items()}
        s = sum(jitter.values())
        self.alloc = {r: v / s for r, v in jitter.items()}
        self.top_cap = self.rng.uniform(*TOP_CAP_RANGE) * b
        pool = sorted(view.pool.values(), key=lambda p: -p.ref_price)
        # giocatore feticcio: 1-2 nomi della fascia medio-alta che "prendo
        # ogni anno" (pattern censito nelle guide) — sopravvaluta del 40%
        self.fetish: set[str] = set()
        mid_high = [p.player_id for p in pool[5:60]]
        if mid_high:
            for _ in range(self.rng.randint(1, 2)):
                self.fetish.add(self.rng.choice(mid_high))
        tiers = self._tiers(pool)
        sigma_prof = self.profile.get("sigma", 0.25)
        for p in pool:
            # spread osservato nelle aste reali (coefficiente di variazione)
            # quando disponibile, altrimenti la sigma del profilo
            if p.ref_price > 0.004 and p.ref_price_sd > 0:
                sigma = min(0.55, max(0.15, p.ref_price_sd / p.ref_price))
            else:
                sigma = sigma_prof
            base = max(1.0, p.ref_price * b)
            w = self.profile.get("blend_w", 0.0)
            if w > 0 and p.player_id in self.hint_prices:
                base = (1 - w) * base + w * max(1.0, self.hint_prices[p.player_id])
            v = base * self.rng.lognormvariate(0, sigma)
            v *= self.profile.get("value_mult", 1.0)
            t = tiers[p.player_id]
            if t == "top":
                v *= self.profile.get("top_mult", 1.0)
            elif t == "mid":
                v *= self.profile.get("mid_mult", 1.0)
            else:
                v *= self.profile.get("scrub_mult", 1.0)
            if self.fav_team and p.team == self.fav_team:
                v *= self.profile.get("team_bias", 1.0)
            if p.player_id in self.fetish:
                v *= 1.4
            self.values[p.player_id] = v

    @staticmethod
    def _tiers(pool_sorted: list[Player]) -> dict[str, str]:
        out = {}
        by_role: dict[str, list[Player]] = {}
        for p in pool_sorted:
            by_role.setdefault(p.role, []).append(p)
        for ps in by_role.values():
            n = len(ps)
            for i, p in enumerate(ps):
                out[p.player_id] = "top" if i < max(3, n // 20) else (
                    "mid" if i < n // 3 else "scrub")
        return out

    # ---------- comportamento ----------
    def _willingness(self, view: AuctionView, player: Player) -> float:
        v = self.values.get(player.player_id, 1.0)
        if self.profile_name == "ancorato" and view.sold:
            recent = [pr for pid, _, pr in view.sold[-6:]
                      if abs(self.values.get(pid, 0) - v) < 0.35 * max(v, 1)]
            if recent:
                w = self.profile["anchor_w"]
                v = (1 - w) * v + w * (sum(recent) / len(recent)) * 1.08
        if self.profile_name == "panic":
            v *= min(self.profile["panic_cap"],
                     1 + self.profile["panic_step"] * self.lost_targets)
        # disciplina morbida di reparto: oltre il budget di reparto la voglia cala
        role = player.role
        spent = sum(pr for _, pr in view.me.roster[role])
        room = self.alloc[role] * view.budget_total - spent
        if v > room:
            v = room + (v - room) * 0.45   # gli umani sforano, ma non all'infinito
        # pressione di fine reparto: pochi giocatori decenti rimasti -> alza
        need = view.me.slots_left(view.quotas, role)
        decent = sum(1 for p in view.available(role) if p.ref_price * view.budget_total > 3)
        if need > 0 and decent < need * 3:
            v *= 1.15
        # adattamento all'inflazione di stanza: i crediti non spesi valgono zero,
        # gli umani lo sentono e alzano le valutazioni quando gira tanto denaro
        infl = view.inflation()
        v *= min(2.2, max(0.75, infl ** 0.6))
        # ritmo di spesa: se sto accumulando crediti rispetto agli slot che
        # mi restano, mollo i freni (anche il tirchio, tardi e a malincuore)
        empty_frac = view.me.slots_left(view.quotas) / sum(view.quotas.values())
        if empty_frac > 0:
            pace = view.me.budget / (view.budget_total * empty_frac)
            v *= min(1.5, max(1.0, pace ** 0.4))
        # tetto umano sul singolo (fix realismo: top reali max ~0.42 budget)
        return max(1.0, min(v, getattr(self, "top_cap", view.budget_total * 0.42)))

    def bid(self, view: AuctionView, player: Player, price: int, leader) -> BidDecision:
        v = self._willingness(view, player)
        nxt = price + 1
        if nxt <= v:
            # salto occasionale per scoraggiare (comportamento umano)
            jump = nxt
            if self.rng.random() < 0.12 and v - nxt > 4:
                jump = nxt + int((v - nxt) * self.rng.uniform(0.2, 0.5))
            return BidDecision(jump, self._thought_bid(player, v))
        # enforcer: alza il prezzo su giocatori che non vuole, se margine di sicurezza
        if (self.profile_name == "enforcer"
                and self.rng.random() < self.profile["enforce_p"]
                and nxt <= self.profile["enforce_margin"] * player.ref_price * view.budget_total):
            return BidDecision(nxt, f"lo faccio pagare ({nxt})")
        if v >= player.ref_price * view.budget_total * 0.9:
            self.lost_targets += 1 if nxt > v else 0
        return BidDecision(None, f"troppo per me (valuto {v:.0f})")

    def nominate(self, view: AuctionView) -> NominationDecision:
        role = view.current_role
        avail = sorted(view.available(role),
                       key=lambda p: -self.values.get(p.player_id, 0))
        pick = avail[0]
        if self.profile_name == "tifoso":
            mine = [p for p in avail if p.team == self.fav_team]
            if mine and self.rng.random() < 0.6:
                pick = mine[0]
        elif self.rng.random() < 0.35 and len(avail) > 10:
            pick = self.rng.choice(avail[:10])
        opening = max(1, int(self.values.get(pick.player_id, 1) * 0.25))
        opening = min(opening, view.me.max_bid(view.quotas))
        return NominationDecision(pick.player_id, opening,
                                  self._thought_nom(pick))

    def on_hammer(self, view, player, price, winner):
        if winner != view.me.team_id and self.values.get(player.player_id, 0) > price:
            self.lost_targets += 1

    # ---------- pensieri ----------
    def _thought_bid(self, p: Player, v: float) -> str:
        pool = {
            "tifoso": f"{p.team}? lo voglio" if p.team == self.fav_team else f"vale {v:.0f}",
            "panic": f"non me lo faccio scappare ({v:.0f})",
            "tirchio": f"fino a {v:.0f}, non un credito in piu'",
            "stars_scrubs": f"e' un top, dentro ({v:.0f})",
        }
        return pool.get(self.profile_name, f"per me vale {v:.0f}")

    def _thought_nom(self, p: Player) -> str:
        if self.profile_name == "tifoso" and p.team == self.fav_team:
            return f"chiamo il mio {p.name}"
        return f"chiamo {p.name}"
