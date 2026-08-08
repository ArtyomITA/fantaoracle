"""Motore d'asta a chiamata: ruoli in blocchi, giro di nomination, rilanci liberi.

Regole implementate (config lega):
- ruoli in ordine P -> D -> C -> A; il blocco finisce quando tutte le squadre
  hanno riempito la quota del ruolo;
- giro di chiamata a rotazione (ordine tavolo da seed), non si puo' saltare;
- prezzo base minimo 1, rilancio minimo +1 (salti consentiti);
- offerta massima = crediti - (slot vuoti totali - 1): resta 1 credito per slot;
- l'asta sul singolo giocatore chiude quando un giro completo di tavolo
  passa senza rilanci: aggiudicato all'ultimo offerente;
- se nessuno rilancia sull'apertura, va al chiamante al prezzo di apertura.

Ogni evento (nomination, singolo rilancio, martelletto) finisce nell'event log
JSONL con il "pensiero" del bot: e' il combustibile del replay di Fase 5.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import ROLES, AuctionEvent, Player, TeamState
from ..bots.base import AuctionView, Bot


class AuctionEngine:
    def __init__(self, players: dict[str, Player], bots: list[Bot],
                 quotas: dict[str, int], budget: int, rng,
                 role_order: tuple[str, ...] = ROLES,
                 min_price: int = 1, min_increment: int = 1,
                 meta: dict | None = None):
        assert len(bots) >= 2
        self.pool = dict(players)
        self.bots = bots
        self.quotas = quotas
        self.budget_total = budget
        self.rng = rng
        self.role_order = role_order
        self.min_price = min_price
        self.min_increment = min_increment
        self.meta = meta or {}
        self.teams = [TeamState(team_id=f"T{i}", bot_name=b.name, budget=budget)
                      for i, b in enumerate(bots)]
        self.sold: list[tuple[str, str, int]] = []
        self.events: list[AuctionEvent] = []
        self._seq = 0
        self._live_fh = None

    # ---------- event log ----------
    def attach_live_log(self, path: str | Path):
        """Scrittura INCREMENTALE: ogni evento su disco appena emesso.
        Un crash non perde mai la storia dell'asta."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._live_fh = open(p, "a", encoding="utf-8")
        for e in self.events:   # backlog se attaccato a motore gia' partito
            self._live_fh.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
        self._live_fh.flush()

    def _emit(self, kind: str, **payload):
        self._seq += 1
        e = AuctionEvent(self._seq, kind, payload)
        self.events.append(e)
        if self._live_fh is not None:
            self._live_fh.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
            self._live_fh.flush()

    def write_log(self, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for e in self.events:
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

    # ---------- viste ----------
    def _view(self, idx: int, role: str) -> AuctionView:
        return AuctionView(
            me=self.teams[idx],
            others=[t for i, t in enumerate(self.teams) if i != idx],
            quotas=self.quotas,
            budget_total=self.budget_total,
            current_role=role,
            pool=self.pool,
            sold=self.sold,
        )

    # ---------- ripresa da log ----------
    def restore(self, events: list[dict], teams_state: list[dict],
                seating: list[int], nom_ptr: int):
        """Riprende un'asta interrotta: eventi storici preservati (il client
        ricostruisce la scena dal backlog), rose e budget ripristinati.
        Il pool va passato al costruttore GIA' senza i giocatori venduti."""
        self.events = [AuctionEvent(e["seq"], e["kind"],
                                    {k: v for k, v in e.items()
                                     if k not in ("seq", "kind")})
                       for e in events]
        self._seq = self.events[-1].seq if self.events else 0
        for t, st in zip(self.teams, teams_state):
            t.budget = st["budget"]
            t.roster = {r: list(st["roster"].get(r, [])) for r in ROLES}
        self.sold = [(pid, tid, price) for st in teams_state
                     for r, lst in st["roster"].items()
                     for pid, price in lst
                     for tid in (st["team_id"],)]
        self._restore_seating = seating
        self._restore_nom_ptr = nom_ptr

    # ---------- svolgimento ----------
    def run(self) -> list[TeamState]:
        resumed = hasattr(self, "_restore_seating")
        if resumed:
            seating = self._restore_seating
            nom_ptr = self._restore_nom_ptr
            self._emit("resume", note="asta ripresa dal log")
        else:
            seating = list(range(len(self.bots)))
            self.rng.shuffle(seating)
            nom_ptr = 0
            self._emit("auction_start",
                       seating=[self.teams[i].team_id for i in seating],
                       bots=[self.bots[i].name for i in seating],
                       budget=self.budget_total, quotas=self.quotas,
                       **self.meta)
        for i, b in enumerate(self.bots):
            b.start_auction(self._view(i, self.role_order[0]))

        for role in self.role_order:
            if not any(t.slots_left(self.quotas, role) > 0 for t in self.teams):
                continue   # fase gia' completata (ripresa)
            self._emit("phase_start", role=role)
            while any(t.slots_left(self.quotas, role) > 0 for t in self.teams):
                # prossimo chiamante col ruolo ancora aperto (non si salta)
                for _ in range(len(seating)):
                    idx = seating[nom_ptr % len(seating)]
                    nom_ptr += 1
                    if self.teams[idx].slots_left(self.quotas, role) > 0:
                        break
                self._run_lot(idx, role)
        self._emit("auction_end",
                   teams=[{"team_id": t.team_id, "bot": t.bot_name,
                           "budget_left": t.budget,
                           "roster": {r: t.roster[r] for r in ROLES}}
                          for t in self.teams])
        return self.teams

    def _run_lot(self, nominator_idx: int, role: str):
        nom_team = self.teams[nominator_idx]
        decision = self.bots[nominator_idx].nominate(self._view(nominator_idx, role))
        player = self.pool[decision.player_id]
        assert player.role == role, f"{player.name}: chiamato {player.role} nel blocco {role}"
        opening = max(self.min_price, decision.opening_bid)
        opening = min(opening, nom_team.max_bid(self.quotas, self.min_price))
        self._emit("nomination", team=nom_team.team_id, bot=nom_team.bot_name,
                   player_id=player.player_id, player=player.name, role=role,
                   opening=opening, thought=decision.thought)

        price, leader = opening, nominator_idx
        quiet = 0  # squadre consecutive interpellate senza rilancio
        order = [i for i in range(len(self.teams))]
        ptr = (nominator_idx + 1) % len(order)
        while quiet < len(order) - 1:
            idx = order[ptr]
            ptr = (ptr + 1) % len(order)
            if idx == leader:
                continue
            team = self.teams[idx]
            min_next = price + self.min_increment
            if (team.slots_left(self.quotas, role) <= 0
                    or min_next > team.max_bid(self.quotas, self.min_price)):
                quiet += 1
                continue
            d = self.bots[idx].bid(self._view(idx, role), player, price,
                                   self.teams[leader].team_id)
            if d.amount is None or d.amount < min_next:
                quiet += 1
                continue
            amount = min(d.amount, team.max_bid(self.quotas, self.min_price))
            price, leader, quiet = amount, idx, 0
            self._emit("bid", team=team.team_id, bot=team.bot_name,
                       player_id=player.player_id, amount=amount,
                       thought=d.thought)

        winner = self.teams[leader]
        winner.budget -= price
        winner.roster[role].append((player.player_id, price))
        del self.pool[player.player_id]
        self.sold.append((player.player_id, winner.team_id, price))
        self._emit("hammer", team=winner.team_id, bot=winner.bot_name,
                   player_id=player.player_id, player=player.name, role=role,
                   price=price, budget_left=winner.budget)
        for i, b in enumerate(self.bots):
            b.on_hammer(self._view(i, role), player, price, winner.team_id)
