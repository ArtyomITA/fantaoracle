"""Livello 2 — il cubo TABELLINO.

Percorso sperimentale, separato dal simulatore operativo. Genera una stagione
partita per partita seguendo la fattorizzazione:

    stato di squadre e giocatori
        -> risultato della partita          (partita.py)
        -> chi gioca e quanti minuti        (partecipazione.py)
        -> eventi individuali del tabellino (eventi.py)
        -> voto puro dato il tabellino      (voto.py)
        -> punteggio della lega             (punteggio.py)

Ogni pezzo e' stimabile e verificabile da solo; `generatore.py` li mette in
fila e produce gli scenari. Niente qui viene attivato automaticamente nel
Copilota o nell'ottimizzatore: l'integrazione e' selezionabile e la
promozione operativa richiede una decisione esplicita.
"""
