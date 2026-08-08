# -*- coding: utf-8 -*-
"""Indagine: comportamento di B al tavolo (tournament_mod, main_1B_2A_7C, 2024-25 e 2025-26).

Risponde a 5 domande:
1. Selettivita' (lotti con almeno un rilancio di B, distribuzione rilanci/lotto)
2. Nomination di B: drain vs riempitivi + efficacia (prezzo hammer vs ref_price)
3. Spesa di B per ruolo (% del 500) vs consenso guide
4. Residui 2024-25 vs 2025-26: prezzi pagati vs q50
5. Calibrazione in-asta: copertura empirica [q10,q90] sui hammer con q50>10
"""
import sys, json, glob, os, pickle
from collections import Counter, defaultdict
import statistics as st

sys.path.insert(0, r'src')

BASE = r'data\tournament_mod'
SEASONS = ['2024-25', '2025-26']
COMP = 'main_1B_2A_7C'
BUDGET = 500

def load_pack(season):
    with open(rf'data\packs\pack_{season}.pkl', 'rb') as f:
        return pickle.load(f)

def parse_replica(path):
    """Ritorna (b_team, lots). lot = dict(nominator_bot, nom_thought, player_id, player, role,
    opening, bids=[(team,bot,amount)], hammer=(team,bot,price) or None)."""
    lots = []
    cur = None
    b_team = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            ev = json.loads(line)
            k = ev['kind']
            if k == 'auction_start':
                for t, b in zip(ev['seating'], ev['bots']):
                    if b == 'B':
                        b_team = t
            elif k == 'nomination':
                cur = dict(nominator_bot=ev['bot'], nom_team=ev['team'],
                           nom_thought=ev.get('thought', ''),
                           player_id=ev['player_id'], player=ev['player'],
                           role=ev['role'], opening=ev['opening'], bids=[], hammer=None)
            elif k == 'bid' and cur is not None:
                cur['bids'].append((ev['team'], ev['bot'], ev['amount']))
            elif k == 'hammer' and cur is not None:
                cur['hammer'] = (ev['team'], ev['bot'], ev['price'])
                lots.append(cur)
                cur = None
    return b_team, lots


def main():
    out = {}
    for season in SEASONS:
        pack = load_pack(season)
        bp = pack.b_predictions
        players = pack.players
        logs = sorted(glob.glob(os.path.join(BASE, season, COMP, 'logs', 'replica_*.jsonl')))

        n_lots_tot = 0
        n_lots_b_bid = 0
        bids_per_lot = Counter()          # numero di rilanci di B nei lotti dove ne fa >=1
        n_b_nom = 0
        drain_noms = []                   # (player_id, hammer_price, won_by_b)
        filler_noms = []
        b_buys = defaultdict(list)        # role -> [price] (tutti i replicas, per lotto)
        b_buy_rows = []                   # (season, player_id, role, price, q50, q10, q90, ref_cred)
        all_hammer_over_ref = [0, 0]      # sopra_ref, tot (lotti con ref noto, tutte le nomination)
        cover = [0, 0]                    # in [q10,q90], tot (hammer con q50>10)
        market_vs_q50 = []                # price/q50 su tutti gli hammer con q50>=1
        spend_by_role_by_rep = []         # per replica: dict role->spent di B

        for lg in logs:
            b_team, lots = parse_replica(lg)
            rep_spend = defaultdict(int)
            for lot in lots:
                n_lots_tot += 1
                nb = sum(1 for t, b, a in lot['bids'] if b == 'B')
                if nb > 0:
                    n_lots_b_bid += 1
                    bids_per_lot[nb] += 1
                pid = lot['player_id']
                pl = players.get(pid)
                pred = bp.get(pid)
                hprice = lot['hammer'][2] if lot['hammer'] else None
                hbot = lot['hammer'][1] if lot['hammer'] else None
                ref_cred = pl.ref_price * BUDGET if pl else None

                if hprice is not None and ref_cred is not None and ref_cred > 0:
                    all_hammer_over_ref[1] += 1
                    if hprice > ref_cred:
                        all_hammer_over_ref[0] += 1

                if hprice is not None and pred and pred['q50'] > 10:
                    cover[1] += 1
                    if pred['q10'] <= hprice <= pred['q90']:
                        cover[0] += 1
                if hprice is not None and pred and pred['q50'] >= 1:
                    market_vs_q50.append(hprice / pred['q50'])

                if lot['nominator_bot'] == 'B':
                    n_b_nom += 1
                    th = lot['nom_thought']
                    is_drain = 'fatevi male' in th
                    rec = dict(pid=pid, player=lot['player'], price=hprice,
                               ref=ref_cred, won_by_b=(hbot == 'B'), thought=th)
                    (drain_noms if is_drain else filler_noms).append(rec)

                if hbot == 'B' and hprice is not None:
                    rep_spend[lot['role']] += hprice
                    b_buys[lot['role']].append(hprice)
                    if pred:
                        b_buy_rows.append(dict(role=lot['role'], price=hprice,
                                               q50=pred['q50'], q10=pred['q10'],
                                               q90=pred['q90'], ref=ref_cred,
                                               player=lot['player']))
            spend_by_role_by_rep.append(dict(rep_spend))

        # leftover da replicas.jsonl (tutte le repliche, non solo i 6 log)
        leftovers = []
        with open(os.path.join(BASE, season, COMP, 'replicas.jsonl'), encoding='utf-8') as f:
            for line in f:
                d = json.loads(line)
                leftovers.append(d['teams']['B']['leftover'])

        out[season] = dict(
            n_logs=len(logs), n_lots_tot=n_lots_tot, n_lots_b_bid=n_lots_b_bid,
            bids_per_lot=dict(sorted(bids_per_lot.items())),
            n_b_nom=n_b_nom, drain=drain_noms, filler=filler_noms,
            all_hammer_over_ref=all_hammer_over_ref, cover=cover,
            market_vs_q50=market_vs_q50, spend_by_role_by_rep=spend_by_role_by_rep,
            b_buy_rows=b_buy_rows, leftovers=leftovers,
        )

    # ---- stampa risultati ----
    for season in SEASONS:
        d = out[season]
        print('=' * 70)
        print(f'STAGIONE {season}  ({d["n_logs"]} log di replica, {len(d["leftovers"])} repliche totali)')
        print('=' * 70)

        # Q1
        n, nb = d['n_lots_tot'], d['n_lots_b_bid']
        print(f'\n[Q1] Selettivita: B rilancia in {nb}/{n} lotti = {100*nb/n:.1f}%')
        print(f'     Distribuzione n. rilanci di B per lotto (solo lotti con >=1): {d["bids_per_lot"]}')
        tot_bids = sum(k*v for k, v in d['bids_per_lot'].items())
        print(f'     Rilanci totali di B: {tot_bids}, media {tot_bids/max(nb,1):.2f} per lotto attivo')

        # Q2
        dr, fl = d['drain'], d['filler']
        print(f'\n[Q2] Nomination di B: {d["n_b_nom"]} totali -> drain {len(dr)} ({100*len(dr)/d["n_b_nom"]:.1f}%), '
              f'riempitivi {len(fl)} ({100*len(fl)/d["n_b_nom"]:.1f}%)')
        dr_won_b = sum(1 for r in dr if r['won_by_b'])
        fl_won_b = sum(1 for r in fl if r['won_by_b'])
        print(f'     Drain comprati da B stesso: {dr_won_b}/{len(dr)}; riempitivi comprati da B: {fl_won_b}/{len(fl)}')
        dr_ref = [r for r in dr if r['ref'] and r['price'] is not None]
        dr_over = sum(1 for r in dr if r['ref'] and r['price'] is not None and r['price'] > r['ref'])
        base_over, base_tot = d['all_hammer_over_ref']
        print(f'     Drain aggiudicati sopra ref_price: {dr_over}/{len(dr_ref)} = {100*dr_over/max(len(dr_ref),1):.1f}%')
        print(f'     Media di TUTTI i lotti sopra ref_price: {base_over}/{base_tot} = {100*base_over/base_tot:.1f}%')
        prem = [r['price']/r['ref'] for r in dr_ref if r['ref'] > 0]
        print(f'     Premio medio prezzo/ref sui drain: {st.mean(prem):.2f}x (mediana {st.median(prem):.2f}x)')

        # Q3
        reps = d['spend_by_role_by_rep']
        print(f'\n[Q3] Spesa media di B per ruolo (% del 500, media su {len(reps)} repliche loggate):')
        guide = {'P': (6, 9), 'D': (12, 16), 'C': (24, 30), 'A': (50, 64)}
        for role in 'PDCA':
            v = [100 * r.get(role, 0) / BUDGET for r in reps]
            g = guide[role]
            print(f'     {role}: {st.mean(v):5.1f}%  (min {min(v):.1f}, max {max(v):.1f})   guide: {g[0]}-{g[1]}%')
        tot_spent = [sum(r.values()) for r in reps]
        print(f'     Spesa totale media: {st.mean(tot_spent):.0f}/{BUDGET}')

        # Q4
        lo = d['leftovers']
        print(f'\n[Q4] Leftover B su {len(lo)} repliche: media {st.mean(lo):.0f}, mediana {st.median(lo):.0f}, '
              f'min {min(lo)}, max {max(lo)}, p10 {st.quantiles(lo, n=10)[0]:.0f}, p90 {st.quantiles(lo, n=10)[-1]:.0f}')
        rows = d['b_buy_rows']
        ratio = [r['price'] / r['q50'] for r in rows if r['q50'] >= 1]
        below = sum(1 for r in rows if r['q50'] >= 1 and r['price'] < r['q50'])
        nn = sum(1 for r in rows if r['q50'] >= 1)
        print(f'     Acquisti B (q50>=1): {nn}; pagato/q50 medio {st.mean(ratio):.2f}x, mediana {st.median(ratio):.2f}x; '
              f'sotto q50: {below}/{nn} = {100*below/nn:.1f}%')
        mkt = d['market_vs_q50']
        print(f'     Mercato intero: prezzo/q50 medio {st.mean(mkt):.2f}x, mediana {st.median(mkt):.2f}x (n={len(mkt)})')
        # quanto pagano i big (q50>20) rispetto a q50, mercato
        # ripasso: usa b_buy_rows con q50>10
        big = [r['price']/r['q50'] for r in rows if r['q50'] > 10]
        if big:
            print(f'     Acquisti B con q50>10: n={len(big)}, pagato/q50 medio {st.mean(big):.2f}x')

        # Q5
        c_in, c_tot = d['cover']
        print(f'\n[Q5] Copertura [q10,q90] sui hammer con q50>10: {c_in}/{c_tot} = {100*c_in/c_tot:.1f}% '
              f'(target nominale 80%)')
        print()

if __name__ == '__main__':
    main()
