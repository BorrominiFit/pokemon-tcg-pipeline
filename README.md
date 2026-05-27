# Pokémon TCG Weekly Investing Pipeline

Pipeline automatizzata che ogni **lunedì alle 08:00 (Europe/Rome)** analizza il mercato del sigillato Pokémon TCG (EU/IT), produce una strategia d'acquisto prioritizzata, crea un evento su **Google Calendar** con le top 3 azioni e aggiorna una **dashboard web** interattiva.

Tutto su free tier: **GitHub Actions** (scheduler + esecuzione) + **GitHub Pages** (dashboard) + **Google Calendar API** (evento).

---

## 1. Architettura consigliata

### Confronto soluzioni valutate

| Criterio                | Google Apps Script       | Python su cloud free tier (Render/Railway) | Python su Google Cloud Run | **Python + GitHub Actions** ⭐ |
| ----------------------- | ------------------------ | ------------------------------------------ | -------------------------- | ------------------------------ |
| Costo mensile           | €0                       | €0 con limiti (cold start, sleep 15 min)   | €0 sotto soglia, poi pay   | **€0**                         |
| Affidabilità cron       | Buona                    | Bassa (cold start, sleep)                  | Ottima                     | **Ottima**                     |
| Capacità scraping       | Limitata (UrlFetch quota)| Ottima                                     | Ottima                     | **Ottima**                     |
| Dashboard hosting       | Apps Script Web App      | Static site separato                       | Cloud Storage / Firebase   | **GitHub Pages incluso**       |
| Storage storico         | Sheets                   | DB esterno o filesystem effimero           | Firestore                  | **Repo git (commit JSON)**     |
| Manutenibilità non-dev  | Media                    | Bassa                                      | Bassa                      | **Alta** (tutto in repo)       |
| Setup iniziale          | Veloce                   | Medio                                      | Complesso                  | **Medio**                      |

**Scelta: GitHub Actions + GitHub Pages** perché unisce zero costi, scheduling robusto, hosting dashboard incluso, storia versionata gratis (i JSON storici sono committati nella repo) e zero infrastruttura da gestire.

### Schema architetturale

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions (cron lunedì 06:00 UTC)                          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  src/main.py — orchestrator                                │ │
│  │                                                            │ │
│  │   1. carica YAML (sources, weights, products)              │ │
│  │   2. avvia scrapers ──────► PokéBeach, Pokeguardian,       │ │
│  │                              Cardmarket, Pokemon.com,      │ │
│  │                              Reddit (JSON pubblico)        │ │
│  │   3. signal_engine ─► score 0-100 per prodotto             │ │
│  │   4. strategy_builder ─► PREORDER/ACCUMULATE/HOLD/AVOID    │ │
│  │   5. data/latest.json + data/history/YYYY-Wxx.json         │ │
│  │   6. Google Calendar API ─► evento lun 08:00 + reminder    │ │
│  └────────────────────────────────────────────────────────────┘ │
│           │                                                      │
│           ▼ commit data/                                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Job deploy-pages → GitHub Pages                           │ │
│  │  dashboard/ (HTML + Chart.js + Grid.js) legge data/        │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │                                          │
         ▼                                          ▼
   ┌──────────────────┐                  ┌─────────────────────┐
   │ Google Calendar  │                  │ Dashboard pubblica  │
   │ Evento lun 08:00 │                  │ <user>.github.io/.. │
   │ + reminder 1d/1h │                  │ tabella + grafici   │
   └──────────────────┘                  └─────────────────────┘
```

---

## 2. Stack tecnologico

**Backend (Python 3.11)**
- `requests` + `tenacity` — HTTP + retry esponenziali
- `beautifulsoup4` + `lxml` — parsing HTML
- `pyyaml` — config
- `google-api-python-client`, `google-auth` — Calendar API

**Frontend dashboard (zero build, CDN puro)**
- `gridjs` — tabella ordinabile/filtrable/searchable
- `chart.js` — grafici trend storico

**Infra (tutti free tier permanenti)**
- **GitHub Actions** — 2000 min/mese su repo private, illimitato su public. Una run pesa ~30-60s → ~3 min/mese.
- **GitHub Pages** — hosting statico illimitato per repo pubblica.
- **Google Calendar API** — 1.000.000 query/giorno gratis.

**Costo totale stimato: 0 €/mese.**

---

## 3. Struttura della repo

```
.
├── .github/workflows/weekly-strategy.yml   # cron + deploy Pages
├── src/
│   ├── main.py                              # entry point
│   ├── config/
│   │   ├── sources.yaml                     # fonti scraping
│   │   ├── weights.yaml                     # pesi segnali + soglie
│   │   └── products.yaml                    # prodotti monitorati
│   ├── scrapers/
│   │   ├── base.py                          # classe base (retry, cache, UA)
│   │   ├── pokebeach.py
│   │   ├── pokeguardian.py
│   │   ├── cardmarket.py
│   │   ├── pokemon_official.py
│   │   └── reddit_pokeinvesting.py
│   ├── analyzers/
│   │   ├── signal_engine.py                 # score 0-100 per prodotto
│   │   └── strategy_builder.py              # raccomandazioni + budget
│   ├── integrations/
│   │   ├── data_persistence.py              # JSON output + history
│   │   └── google_calendar.py               # evento settimanale
│   └── utils/
│       ├── logger.py
│       └── cache.py                         # cache disco delle GET
├── dashboard/
│   ├── index.html
│   ├── style.css
│   └── app.js                               # Chart.js + Grid.js
├── data/                                    # output (auto-commit)
│   ├── latest.json
│   └── history/YYYY-Wxx.json
├── requirements.txt
├── .env.example
└── README.md
```

---

## 4. Setup step-by-step

### 4.1 Fork/crea la repo

1. Crea una nuova repo GitHub (può essere pubblica per Pages illimitato, o privata se preferisci — userai parte dei 2000 min/mese gratuiti).
2. Carica tutti i file di questo progetto. In alternativa, da terminale:
   ```bash
   cd "Pokemon scanning script"
   git init && git add . && git commit -m "init pipeline"
   git remote add origin git@github.com:<tuo-user>/<nome-repo>.git
   git branch -M main && git push -u origin main
   ```

### 4.2 Setup Google Calendar API (Service Account)

Questa è la parte più "noiosa" ma si fa una volta sola. Servono ~10 minuti.

1. Vai su **[Google Cloud Console](https://console.cloud.google.com/)** → crea un nuovo progetto (es. `pokemon-pipeline`).
2. Nel menu laterale: **APIs & Services → Library** → cerca **Google Calendar API** → clicca **Enable**.
3. **APIs & Services → Credentials → Create Credentials → Service account**.
   - Nome: `pokemon-pipeline-sa`. Crea senza ruoli specifici.
4. Dopo la creazione, clicca sul service account → tab **Keys → Add Key → Create new key → JSON**. Scarica il file `.json`.
5. Apri il file scaricato e copia il valore del campo `client_email` (es. `pokemon-pipeline-sa@xxx.iam.gserviceaccount.com`).
6. Vai su **[Google Calendar](https://calendar.google.com/)** sul tuo account personale:
   - Settings → seleziona il calendario in cui vuoi gli eventi → **Share with specific people** → **Add people** → incolla la `client_email` del service account → **Make changes to events** → invia.
   - Sempre nelle settings del calendario, copia il **Calendar ID** (formato `xxxxx@group.calendar.google.com`, oppure usa `primary` per il calendario principale dell'account a cui hai condiviso).

### 4.3 Configura i Secrets della repo GitHub

Repo → **Settings → Secrets and variables → Actions → New repository secret**. Crea:

| Nome                            | Valore                                                                              |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| `GOOGLE_SERVICE_ACCOUNT_JSON`   | **L'intero contenuto** del file JSON scaricato al punto 4.2.4, incollato così com'è |
| `GOOGLE_CALENDAR_ID`            | Il Calendar ID del 4.2.6 (oppure `primary`)                                         |
| `DASHBOARD_URL`                 | URL Pages: `https://<tuo-user>.github.io/<nome-repo>/` (lo conosci dopo step 4.4)   |
| `SCRAPER_USER_AGENT`            | Un User-Agent realistico — esempio nel `.env.example`                               |

### 4.4 Attiva GitHub Pages

Repo → **Settings → Pages**:
- **Source**: GitHub Actions
- Salva. Al primo run del workflow, Pages verrà popolato automaticamente.

### 4.5 Primo run manuale

Repo → **Actions → Weekly Pokémon TCG Strategy → Run workflow** (dal branch `main`).

Atteso:
- log job `run-pipeline` con segnali scrapati e raccomandazioni;
- commit automatico in `data/`;
- job `deploy-pages` verde;
- evento creato nel Calendar (lunedì 08:00 prossimo);
- dashboard visibile a `https://<tuo-user>.github.io/<nome-repo>/`.

### 4.6 Esecuzione locale (opzionale, per debug)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # editare i valori
export $(grep -v '^#' .env | xargs)
DRY_RUN=true python -m src.main   # salta Calendar API
```

---

## 5. Manutenzione e iterazione

### Come aggiungere un prodotto
Edita `src/config/products.yaml`, aggiungi un blocco con almeno `id`, `set_name`, `product_type`, `release_date`. Il prossimo run lo includerà.

### Come aggiungere una fonte
1. Crea `src/scrapers/<nome>.py` ereditando da `BaseScraper`, implementa `fetch_signals()`.
2. Aggiungi blocco in `src/config/sources.yaml` con `enabled: true`.
3. Registralo in `src/main.py::build_scrapers()`.

### Come tarare i pesi
Modifica `src/config/weights.yaml`. Suggerimenti operativi:
- Se la strategia è troppo "aggressiva" (troppi PREORDER), alza `preorder_min_score` (75 → 80).
- Se vuoi premiare carte chase iconiche, alza `chase_strength_weight`.
- Se hai dati prezzo affidabili e vuoi più peso al timing, alza `premium_msrp_weight`.

### Cosa monitorare nel tempo
- **Log delle GitHub Actions**: se uno scraper inizia a fallire (cambio HTML), il log lo mostra. Aggiorna il selettore CSS in `src/scrapers/<scraper>.py`.
- **Premium MSRP**: se i premi salgono molto sopra il 100%, il sistema declassa automaticamente i prodotti — coerente con strategia long-term.
- **Storico in `data/history/`**: dopo 4-8 settimane avrai trend significativi visibili nel grafico in dashboard.

### Upgrade futuri (roadmap suggerita)
1. **Cardmarket API ufficiali** (richiede account Pro) → sostituire scraper con client API stabile.
2. **POP report PSA** → aggiungere scraper su `psacard.com/pop` per le chase di ogni set.
3. **Notifiche Telegram** → aggiungere in `src/integrations/` un publisher su bot Telegram per allerte real-time fuori cadenza settimanale.
4. **Backtesting**: con almeno 6 mesi di history JSON, scrivere uno script che misura quanto le raccomandazioni passate hanno performato e auto-tunare i pesi.

### Quando aspettarsi falsi positivi/negativi
- Set freschi appena annunciati hanno poco materiale Reddit/news → `hype` e `scarcity` neutri → score sottostimato. È un comportamento corretto (long-term).
- Premium MSRP `null` (scraping Cardmarket fallito) → score neutro 0.5 sul componente. Riprova al run successivo o usa la cache.

---

## Sorgenti dati utilizzate

Tutti gli scraper usano **endpoint pubblici** senza autenticazione. Rispetta i ToS delle fonti (no high-frequency). Lo `rate_limit_seconds` in `sources.yaml` è impostato in modo conservativo.

---

**Disclaimer**: questo strumento produce segnali di analisi quantitativa per supportare decisioni d'investimento personali. Non costituisce consulenza finanziaria. Il mercato del collezionismo è illiquido e può perdere valore.
