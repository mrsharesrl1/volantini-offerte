"""
SCRAPER VOLANTINI SUPERMERCATI ITALIANI
Scarica le offerte settimanali dai siti ufficiali e salva in offerte.json
"""

import json
import re
import time
import os
from datetime import datetime, date
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

# ============================================================
# CONFIGURAZIONE — modifica qui i supermercati che ti interessano
# ============================================================
SUPERMERCATI = {
    "Lidl":     "https://www.lidl.it/it/offerte",
    "Eurospin": "https://www.eurospin.it/offerte/",
    "Penny":    "https://www.penny.it/offerte",
    "Conad":    "https://www.conad.it/promozioni.html",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OUTPUT_FILE = "offerte.json"

# ============================================================
# PARSER HTML GENERICO
# ============================================================
class OffertaParser(HTMLParser):
    """Parser HTML minimale — estrae testo da tag comuni usati per offerte."""

    def __init__(self):
        super().__init__()
        self.offerte_testo = []
        self._corrente = []
        self._in_offerta = False
        self._depth = 0
        # Classi CSS tipicamente usate per blocchi offerta nei siti GDO italiani
        self._classi_target = {
            "offer", "offerta", "promo", "promotion", "product",
            "prodotto", "tile", "card", "item", "deal", "sconto",
            "saving", "discount", "weekly", "settimanale",
        }

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classe = (attrs_dict.get("class") or "").lower()
        data_id = attrs_dict.get("data-product-name", "")

        # Attiva cattura se la classe contiene parole chiave offerta
        if any(k in classe for k in self._classi_target) or data_id:
            self._in_offerta = True
            self._depth = 0
            self._corrente = []

        if self._in_offerta:
            self._depth += 1

    def handle_endtag(self, tag):
        if self._in_offerta:
            self._depth -= 1
            if self._depth <= 0:
                testo = " ".join(self._corrente).strip()
                testo = re.sub(r'\s+', ' ', testo)
                if len(testo) > 10:
                    self.offerte_testo.append(testo)
                self._in_offerta = False
                self._corrente = []

    def handle_data(self, data):
        if self._in_offerta:
            testo = data.strip()
            if testo:
                self._corrente.append(testo)


# ============================================================
# ESTRAZIONE OFFERTE DAL TESTO GREZZO
# ============================================================
def estrai_offerte_da_testo(testo_grezzo, supermercato):
    """
    Analisi euristica del testo HTML per identificare blocchi offerta.
    Cerca pattern tipo: nome prodotto + prezzo con € o sconti in %.
    """
    offerte = []

    # Pattern prezzo: €2,99 o 2.99 € o €2.99
    pattern_prezzo = re.compile(
        r'(?:€\s*)?(\d{1,3}[.,]\d{2})\s*€?', re.IGNORECASE
    )
    # Pattern sconto percentuale
    pattern_sconto = re.compile(
        r'(-?\d{1,2})\s*%', re.IGNORECASE
    )
    # Pattern "valido fino" o date
    pattern_data = re.compile(
        r'(?:fino al|al|dal|scade)\s*(\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?)',
        re.IGNORECASE
    )

    for blocco in testo_grezzo:
        # Salta blocchi troppo corti o che non sembrano offerte
        if len(blocco) < 8 or len(blocco) > 500:
            continue

        prezzi   = pattern_prezzo.findall(blocco)
        sconti   = pattern_sconto.findall(blocco)
        date_val = pattern_data.findall(blocco)

        # Serve almeno un prezzo o uno sconto per considerarlo offerta
        if not prezzi and not sconti:
            continue

        # Nome prodotto = prima parte del blocco prima del prezzo/sconto
        nome_raw = re.split(r'€|\d{1,3}[.,]\d{2}|%', blocco)[0].strip()
        nome_raw = re.sub(r'[^\w\s&\',.\-]', ' ', nome_raw)
        nome_raw = re.sub(r'\s+', ' ', nome_raw).strip()

        if not nome_raw or len(nome_raw) < 4:
            continue

        prezzo_offerta  = ("€" + prezzi[0])  if prezzi              else ""
        prezzo_originale= ("€" + prezzi[1])  if len(prezzi) > 1     else ""
        sconto          = (sconti[0] + "%")   if sconti              else ""
        valido_fino     = date_val[0]          if date_val            else ""

        offerte.append({
            "product":       nome_raw[:80],
            "supermarket":   supermercato,
            "category":      "Altro",          # categorizzazione AI separata
            "priceOffer":    prezzo_offerta,
            "priceOriginal": prezzo_originale,
            "discount":      sconto,
            "validUntil":    valido_fino,
            "notes":         "",
            "source":        "scraper_auto",
            "scraped_at":    datetime.now().isoformat(),
        })

    return offerte


# ============================================================
# SCRAPING DI UN SINGOLO SITO
# ============================================================
def scrapa_sito(nome, url):
    print(f"  → Scraping {nome}: {url}")
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            html_bytes = resp.read()

        # Prova UTF-8, fallback latin-1
        try:
            html = html_bytes.decode("utf-8")
        except UnicodeDecodeError:
            html = html_bytes.decode("latin-1", errors="replace")

        parser = OffertaParser()
        parser.feed(html)

        offerte = estrai_offerte_da_testo(parser.offerte_testo, nome)
        print(f"     ✓ Trovati {len(offerte)} blocchi offerta")
        return offerte

    except HTTPError as e:
        print(f"     ✗ HTTP {e.code} per {nome}")
        return []
    except URLError as e:
        print(f"     ✗ Errore connessione {nome}: {e.reason}")
        return []
    except Exception as e:
        print(f"     ✗ Errore generico {nome}: {e}")
        return []


# ============================================================
# CARICA OFFERTE ESISTENTI (per non sovrascrivere)
# ============================================================
def carica_esistenti():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                dati = json.load(f)
                return dati.get("offerte", [])
        except Exception:
            pass
    return []


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 55)
    print(f"SCRAPER VOLANTINI — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 55)

    tutte_offerte = []

    for nome, url in SUPERMERCATI.items():
        offerte = scrapa_sito(nome, url)
        tutte_offerte.extend(offerte)
        time.sleep(2)  # pausa cortesia tra un sito e l'altro

    # Aggiungi ID univoci
    for i, o in enumerate(tutte_offerte):
        o["id"] = f"auto_{int(datetime.now().timestamp())}_{i}"

    # Carica offerte precedenti (aggiunte manualmente dall'app)
    esistenti = carica_esistenti()
    # Rimuove vecchie offerte automatiche (mantiene solo quelle manuali)
    manuali = [o for o in esistenti if o.get("source") != "scraper_auto"]

    # Merge: nuove automatiche + manuali salvate
    dati_output = {
        "last_update": datetime.now().isoformat(),
        "week": date.today().isocalendar()[1],
        "total": len(tutte_offerte) + len(manuali),
        "auto_count": len(tutte_offerte),
        "manual_count": len(manuali),
        "offerte": tutte_offerte + manuali,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dati_output, f, ensure_ascii=False, indent=2)

    print("=" * 55)
    print(f"✅ Completato: {len(tutte_offerte)} offerte auto + {len(manuali)} manuali")
    print(f"   Salvato in: {OUTPUT_FILE}")
    print("=" * 55)


if __name__ == "__main__":
    main()
