# -*- coding: utf-8 -*-
"""Approfondimenti: Q2 baseline sui big, Q4 meccanica dei residui, Q5 direzione degli errori."""
import sys, json, glob, os, pickle
from collections import defaultdict, Counter
import statistics as st

sys.path.insert(0, r'src')
BASE = r'data\tournament_mod'
SEASONS = ['2024-25', '2025-26']
COMP = 'main_1B_2A_7C'
BUDGET = 500

def load_pack(season):
    with open(rf'data\packs\pack_{season}.pkl', 'rb') as f:
        return pickle.load(f)

def iter_lots(path):
    cur = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            ev = json.loads(line)
            k = ev['kind']
            if k == 'nomination':
                cur = dict(nominator_bot=ev['bot'], thought=ev.get('thought',''),
                           player_id=ev['player_id'], role=ev['role'], bids=[], hammer=None)
            elif k == 'bid' and cur is not None:
                cur['bids'].append(ev['bot'])
            elif k == 'hammer' and cur is not None:
                cur['hammer'] = (ev['bot'], ev['price'])
                yield cur
                cur = None

for season in SEASONS:
    pack = load_pack(season)
    bp, players = pack.b_predictions, pack.players
    logs = sorted(glob.glob(os.path.join(BASE, season, COMP, 'logs', 'replica_*.jsonl')))
    print('='*70); print(f'STAGIONE {season}'); print('='*70)

    thoughts = Counter()
    drain_refs = []
    over_by_refband = defaultdict(lambda: [0,0])   # band -> [over, tot]
    drain_over = [0,0]
    below_q10 = above_q90 = inside = 0
    mkt_below_q50 = [0,0]        # hammer con q50>10: price<q50
    b_spent_vs_q50 = []          # per replica: (sum price, sum q50) acquisti B
    b_wins_price = {'2024-25': [], '2025-26': []}
    per_rep = []
    for lg in logs:
        sp, sq, nbuy = 0, 0, 0
        for lot in iter_lots(lg):
            pid = lot['player_id']; pl = players.get(pid); pred = bp.get(pid)
            hbot, hprice = lot['hammer']
            ref = pl.ref_price*BUDGET if pl else None
            if lot['nominator_bot']=='B':
                thoughts['drain' if 'fatevi male' in lot['thought'] else 'basso'] += 1
            if ref and ref>0:
                band = '>=20' if ref>=20 else ('10-20' if ref>=10 else ('3-10' if ref>=3 else '<3'))
                over_by_refband[band][1]+=1
                if hprice>ref: over_by_refband[band][0]+=1
                if lot['nominator_bot']=='B' and 'fatevi male' in lot['thought']:
                    drain_refs.append(ref)
                    drain_over[1]+=1
                    if hprice>ref: drain_over[0]+=1
            if pred and pred['q50']>10:
                if hprice<pred['q10']: below_q10+=1
                elif hprice>pred['q90']: above_q90+=1
                else: inside+=1
                mkt_below_q50[1]+=1
                if hprice<pred['q50']: mkt_below_q50[0]+=1
            if hbot=='B':
                sp += hprice; nbuy += 1
                if pred: sq += pred['q50']
        per_rep.append((sp, sq, nbuy))

    print(f'Nomination B thought types: {dict(thoughts)}')
    print(f'ref mediana dei drain: {st.median(drain_refs):.1f} crediti (min {min(drain_refs):.1f}, max {max(drain_refs):.1f})')
    print('Quota lotti aggiudicati sopra ref_price per fascia di ref (tutti i lotti):')
    for band in ['<3','3-10','10-20','>=20']:
        o,t = over_by_refband[band]
        if t: print(f'   ref {band:>5}: {o}/{t} = {100*o/t:.1f}%')
    o,t = drain_over
    print(f'Drain di B sopra ref: {o}/{t} = {100*o/t:.1f}%')

    tot = below_q10+inside+above_q90
    print(f'\n[Q5 dettaglio] hammer q50>10: sotto q10 {below_q10} ({100*below_q10/tot:.1f}%), '
          f'dentro {inside} ({100*inside/tot:.1f}%), sopra q90 {above_q90} ({100*above_q90/tot:.1f}%)')
    print(f'Mercato: hammer (q50>10) sotto q50: {mkt_below_q50[0]}/{mkt_below_q50[1]} = {100*mkt_below_q50[0]/mkt_below_q50[1]:.1f}%')

    print('\n[Q4 dettaglio] per replica loggata: speso B / somma q50 dei suoi acquisti / n acquisti:')
    for i,(sp,sq,nb) in enumerate(per_rep):
        print(f'   rep{i}: speso {sp}, sum q50 {sq:.0f}, rapporto {sp/sq:.2f}, acquisti {nb}')

    # leftover IQR su tutte le repliche
    lo = []
    with open(os.path.join(BASE, season, COMP, 'replicas.jsonl'), encoding='utf-8') as f:
        for line in f:
            lo.append(json.loads(line)['teams']['B']['leftover'])
    q = st.quantiles(lo, n=4)
    print(f'\nLeftover B (150 repliche): Q1 {q[0]:.0f}, mediana {q[1]:.0f}, Q3 {q[2]:.0f}')
    print()
