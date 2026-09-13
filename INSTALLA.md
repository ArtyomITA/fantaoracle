# Installare FantaOracle su un altro computer (per l'asta)

Il repository contiene codice, pagine e report, **non** la cartella `data/`:
dentro ci sono dati scaricati da fonti terze (voti, probabili, rigoristi) e i
registri delle aste vere. Per usare il Copilota servono pochi di quei file, e
si portano a mano in uno zip.

## 1. Sul computer che ha già i dati

```bash
python scripts/prepara_bundle_asta.py
```

Crea `bundle_asta_<stagione>_<data>.zip` nella cartella sopra il progetto
(12 file, meno di un megabyte: pack della stagione, eleggibilità, note
dell'esperto, voti delle ultime due stagioni, mappa dei nomi, ultimo
mercato). Copialo su chiavetta o drive privato. **Non** va su GitHub.

## 2. Sul computer nuovo

Serve Python 3.11 o più recente (https://www.python.org/downloads/, con
«Add python to PATH»). Poi, da un terminale:

```bash
git clone https://github.com/ArtyomITA/fantaoracle.git
cd fantaoracle
python installa.py --bundle "C:\percorso\bundle_asta_2026-27_20260913.zip"
```

`installa.py` crea l'ambiente `.venv`, installa `requirements-asta.txt`
(pandas, numpy, PuLP, psutil), scompatta il bundle in `data/`, verifica i
file e fa una prova di fumo: avvia il Copilota su una porta di prova,
chiede `/copilot/state`, lo spegne. Se lo zip sta accanto a `installa.py`
lo trova da solo. Si può rilanciare: non rifà quello che c'è già.

Opzioni: `--playwright` installa anche Chrome per il ponte FantaAsta;
`--senza-prova` salta la prova di fumo; `--porta-prova N` cambia la porta.

## 3. Avviare

Doppio click su `FantaOracle.bat` (usa `.venv` se c'è), oppure:

```bash
.venv\Scripts\python scripts\fantaoracle_app.py --porta 8899
```

Si apre http://localhost:8899/viz/index.html: **ASTA VERA → Copilota**,
nomi delle 10 squadre, «sono io», avvia. La pagina dell'asta è
`viz/asta.html` (quella classica resta `viz/copilot.html`). Tutto il resto
è in [`GUIDA_ASTA.md`](GUIDA_ASTA.md): registrare a mano, correggere un
lotto, riprendere dopo un riavvio, listino di carta.

## Se qualcosa non va

- `pip install` fallisce: connessione o proxy; rilancia `installa.py`.
- «manca data/packs/CORRENTE.json»: il bundle non è stato scompattato;
  passa `--bundle` con il percorso giusto.
- La prova di fumo non risponde: leggi le ultime righe stampate (di solito
  un pacchetto mancante); `python installa.py --senza-prova` per andare
  avanti comunque.
- Porta 8899 occupata: `--porta 8898` al menu.
