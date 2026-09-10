/* Ponte FantaAsta Live -> Copilota FantaOracle.
 *
 * Gira DENTRO la scheda di FantaAsta Live (fanta-asta-live.fantacalcio.it):
 * ogni 1,5 s legge lo stato che l'app tiene in localStorage
 * ("FANTA-ASTA-2025-LIVE": squadre e picks {index, teamId, playerId, cost}) e
 * manda ogni assegnazione nuova al Copilota locale (POST /copilot/hammer). Gli
 * identificativi dei giocatori sono gli stessi di fantacalcio.it, quindi dello
 * stesso pack. Se un'assegnazione gia' inviata sparisce (annullata o svincolata
 * in FantaAsta) ed e' l'ultima registrata nel Copilota, la annulla; altrimenti
 * avvisa e blocca quell'indice (niente doppioni silenziosi).
 *
 * Squadre: FantaAsta ha id 0..9 e un nome; il Copilota ha i nomi del setup.
 * Si abbina per nome (senza accenti, anche per prefisso); se non c'e'
 * corrispondenza, per posizione. Conviene usare in FantaAsta gli stessi nomi
 * del setup del Copilota. La mappa si ricalcola da sola quando i nomi cambiano.
 *
 * L'app disabilita console.log ("[APP] CONSOLE DISABLED"): qui si usa solo
 * console.warn. In basso a destra compare un riquadro con lo stato del ponte.
 *
 * Uso: incolla tutto nella console (F12) della scheda FantaAsta, oppure usa
 * il bookmarklet generato da scripts/ponte_bookmarklet.py (viz/ponte.html).
 * Parametri: window.PONTE_COPILOTA (default http://127.0.0.1:8770).
 */
(function () {
  if (window.PONTE && window.PONTE.attivo) { console.warn("PONTE gia' attivo"); return; }
  const COP = window.PONTE_COPILOTA || "http://127.0.0.1:8770";
  const KEY = "FANTA-ASTA-2025-LIVE";
  const MEM = "PONTE_INVIATI_" + COP.replace(/[^0-9]/g, "");
  const inviati = JSON.parse(localStorage.getItem(MEM) || "{}");   // rid -> {ok, ordine, index, ...}
  let ordine = Math.max(0, ...Object.values(inviati).map(v => (v && v.ordine != null ? v.ordine + 1 : 0)), 0);
  let nomiCop = null, mappa = null, firmaSquadre = null, occupato = false;
  let ultimoGiro = null, ultimoEsito = "attesa", rete_ko = 0;
  const errori = [];                                   // ultimi 30 avvisi, per stato()
  const piatto = s => String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").trim();
  const salva = () => { try { localStorage.setItem(MEM, JSON.stringify(inviati)); } catch (e) { /* quota */ } };
  const avvisa = (msg, extra) => {
    console.warn("PONTE: " + msg, extra === undefined ? "" : extra);
    errori.push({ t: new Date().toLocaleTimeString(), msg: msg });
    if (errori.length > 30) errori.shift();
  };

  // ---- riquadro di stato (in basso a destra) --------------------------------
  let box = document.getElementById("ponte-fantaoracle-box");
  if (!box) {
    box = document.createElement("div");
    box.id = "ponte-fantaoracle-box";
    box.style.cssText = "position:fixed;right:10px;bottom:10px;width:240px;z-index:2147483647;" +
      "background:rgba(15,20,30,0.78);color:#e8f0ff;font:12px/1.35 system-ui,Arial,sans-serif;" +
      "padding:8px 10px;border-radius:8px;pointer-events:none;white-space:pre-line;" +
      "box-shadow:0 2px 8px rgba(0,0,0,.35)";
    (document.body || document.documentElement).appendChild(box);
  }
  function dipingi() {
    const n = Object.values(inviati).filter(v => v && v.ok).length;
    const ora = ultimoGiro ? new Date(ultimoGiro).toLocaleTimeString() : "--:--:--";
    const col = ultimoEsito === "OK" ? "#7ee787" : (ultimoEsito === "attesa" ? "#e8f0ff" : "#ff7b72");
    box.innerHTML = "<b>PONTE</b>: " + n + " assegnazioni inviate\nultimo giro " + ora +
      " · <span style=\"color:" + col + "\">" + ultimoEsito + "</span>";
  }
  dipingi();

  // ---- rete -----------------------------------------------------------------
  async function api(path, body) {
    const r = await fetch(COP + path, body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {});
    let d = null;
    try { d = await r.json(); } catch (e) { d = null; }
    return { ok: r.ok, code: r.status, d: d || {} };
  }

  function utente() {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    let d;
    try { d = JSON.parse(raw); } catch (e) { return null; }
    const us = Object.values(d._users || {});
    return us.find(u => u.started && Array.isArray(u.picks)) || us.find(u => Array.isArray(u.picks)) || us[0] || null;
  }

  function nomeGiocatore(u, pid) {
    const p = (u.players || []).find(x => String(x.id) === String(pid));
    return p ? (p.name || p.playerName || ("#" + pid)) : ("#" + pid);
  }

  async function mappaSquadre(u) {
    if (!nomiCop || !nomiCop.length) nomiCop = (await api("/copilot/state")).d.names || [];
    mappa = {};
    const presi = new Set();
    (u.teams || []).forEach(t => {
      let idx = nomiCop.findIndex((n, i) => !presi.has(i) && t.name && piatto(n) === piatto(t.name));
      if (idx < 0 && t.name) {
        idx = nomiCop.findIndex((n, i) => !presi.has(i) && piatto(n).length >= 3 && piatto(t.name).length >= 3 && (piatto(n).startsWith(piatto(t.name)) || piatto(t.name).startsWith(piatto(n))));
      }
      if (idx >= 0) presi.add(idx);
      mappa[t.id] = idx >= 0 ? idx : null;
    });
    (u.teams || []).forEach((t, pos) => {                 // resto per posizione
      if (mappa[t.id] == null && pos < nomiCop.length && !presi.has(pos)) { mappa[t.id] = pos; presi.add(pos); }
    });
    firmaSquadre = (u.teams || []).map(t => t.id + ":" + (t.name || "")).join("|");
    console.warn("PONTE mappa squadre FantaAsta -> Copilota: " +
      (u.teams || []).map(t => (t.name || "#" + t.id) + " -> " + (mappa[t.id] == null ? "?" : nomiCop[mappa[t.id]])).join(" | "));
  }

  function rid(p) { return "fa-" + p.index + "-" + p.playerId + "-" + p.teamId + "-" + p.cost; }
  const vivi = () => Object.keys(inviati).filter(k => inviati[k] && inviati[k].ok);
  const ultimoVivo = () => vivi().sort((a, b) => inviati[b].ordine - inviati[a].ordine)[0];
  // indici con un avviso aperto: li si lascia stare finche' l'utente non sistema
  const bloccato = i => Object.values(inviati).some(v => v && v.avviso && v.index === i);

  async function giro() {
    if (occupato) return;
    occupato = true;
    let esito = "OK";
    try {
      const u = utente();
      if (!u) { ultimoGiro = Date.now(); ultimoEsito = "attesa"; dipingi(); return; }
      const firma = (u.teams || []).map(t => t.id + ":" + (t.name || "")).join("|");
      if (!mappa || firma !== firmaSquadre) await mappaSquadre(u);

      const tutti = u.picks || [];
      const attivi = tutti.filter(p => !p.released);
      const presenti = new Set(attivi.map(rid));
      const svincolati = new Set(tutti.filter(p => p.released).map(rid));

      // 1) sparizioni: annullate, svincolate, o cambiate (costo/squadra a
      //    parita' di index -> il rid cambia, quindi il vecchio sparisce)
      const spariti = Object.keys(inviati)
        .filter(k => inviati[k] && inviati[k].ok && !presenti.has(k))
        .sort((a, b) => inviati[b].ordine - inviati[a].ordine);
      for (const k of spariti) {
        const v = inviati[k];
        const causa = svincolati.has(k) ? "svincolato"
          : (attivi.some(p => p.index === v.index) ? "assegnazione modificata" : "annullata in FantaAsta");
        if (k === ultimoVivo()) {
          const r = await api("/copilot/undo", { richiesta_id: "fa-undo-" + k });
          if (r.d && r.d.ok) {
            console.warn("PONTE annullato nel Copilota (" + causa + "): " + k);
            delete inviati[k]; salva();
          } else {
            esito = "ERRORE";
            avvisa("undo rifiutato dal Copilota per " + k, r.d);
          }
        } else {
          esito = "ERRORE";
          avvisa(causa + " ma non e' l'ultima registrata nel Copilota: annullala a mano (" + k + ")");
          v.ok = false; v.avviso = true; salva();
        }
      }

      // 2) nuove assegnazioni, in ordine di index
      for (const p of attivi.slice().sort((a, b) => a.index - b.index)) {
        const k = rid(p);
        const v = inviati[k];
        if (v && (v.ok || v.errore)) continue;            // gia' fatto o gia' rifiutato
        if (bloccato(p.index)) {                          // avviso aperto su questo lotto
          if (!v) { inviati[k] = { ok: false, avviso: true, index: p.index, ordine: ordine++ }; salva(); }
          continue;
        }
        const ti = mappa[p.teamId];
        if (ti == null) { esito = "ERRORE"; avvisa("squadra non mappata (teamId " + p.teamId + ")"); continue; }
        const body = { player_id: String(p.playerId), team_index: ti,
                       price: Math.max(1, Math.round(p.cost || 1)), richiesta_id: k };
        let r;
        try {
          r = await api("/copilot/hammer", body);
        } catch (e) {                                     // Copilota spento o LNA bloccato
          rete_ko++;
          esito = "ERRORE";
          avvisa("Copilota non raggiungibile (" + (e && e.message ? e.message : e) + "), riprovo al giro dopo");
          break;                                          // niente accumulo: si riprende da qui
        }
        rete_ko = 0;
        if (r.d && r.d.ok) {
          inviati[k] = { ok: true, ordine: ordine++, index: p.index, teamId: p.teamId,
                         playerId: p.playerId, cost: p.cost }; salva();
          console.warn("PONTE ok: " + nomeGiocatore(u, p.playerId) + " -> " + nomiCop[ti] + " a " + body.price +
            (r.d.nota ? " (" + r.d.nota + ")" : ""));
        } else {
          const err = (r.d && r.d.err) || ("HTTP " + r.code);
          inviati[k] = { ok: false, errore: err, ordine: ordine++, index: p.index }; salva();
          esito = "ERRORE";
          if (/inesistente/i.test(String(err))) {
            avvisa("giocatore non presente nel pack: " + nomeGiocatore(u, p.playerId) +
                   " (id " + p.playerId + ") - registralo a mano nel Copilota");
          } else {
            avvisa("rifiutato dal Copilota: " + nomeGiocatore(u, p.playerId) + " -> " + err);
          }
        }
      }
    } catch (e) {
      esito = "ERRORE";
      avvisa("errore nel giro: " + (e && e.message ? e.message : e));
    } finally {
      ultimoGiro = Date.now();
      ultimoEsito = esito;
      dipingi();
      occupato = false;
    }
  }

  const timer = setInterval(giro, 1500);
  giro();
  window.PONTE = {
    attivo: true,
    copilota: COP,
    inviati: inviati,
    ferma: () => {
      clearInterval(timer); window.PONTE.attivo = false;
      ultimoEsito = "fermato"; dipingi();
      console.warn("PONTE fermato");
    },
    rimappa: () => { mappa = null; nomiCop = null; firmaSquadre = null; },
    azzera: () => { for (const k in inviati) delete inviati[k]; salva(); dipingi(); },
    // sblocca un lotto con avviso aperto, dopo aver sistemato a mano il Copilota
    sblocca: (i) => {
      Object.keys(inviati).forEach(k => { if (inviati[k] && inviati[k].index === i) delete inviati[k]; });
      salva(); console.warn("PONTE lotto " + i + " sbloccato");
    },
    stato: () => ({ inviati: JSON.parse(JSON.stringify(inviati)), mappa: mappa,
                    ultimoGiro: ultimoGiro, esito: ultimoEsito, errori: errori.slice() })
  };
  console.warn("PONTE attivo verso " + COP + " (window.PONTE.ferma() per fermarlo, window.PONTE.stato() per lo stato)");
})();
