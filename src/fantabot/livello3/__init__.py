"""Livello 3 — scelta della rosa e della politica d'asta per P(1 posto).

Tre componenti, con interfacce esplicite:

    valutatore.py   da un cubo di stagioni simulate e da rose esclusive:
                    punteggi, gol da fasce, classifica H2H, vincitori
    ricerca.py      generazione e confronto di rose candidate sull'obiettivo
                    campionario P(1 posto)  (SAA)
    indifferenza.py prezzo di indifferenza: differenza fra comprare e passare,
                    con completamento dell'asta da entrambe le parti

Nessuno di questi moduli e' collegato al Copilota o all'ottimizzatore
operativo. L'integrazione e' selezionabile e la promozione richiede una
decisione esplicita.
"""
