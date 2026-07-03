# Source List — RAG Mutual Fund FAQ Bot

**AMC:** ICICI Prudential Asset Management Company  
**Compiled:** June 26, 2026  
**Ingestion corpus:** 13 sources (8 remote URLs + 1 local FAQ bundle + 4 TER scheme rows)

---

## Note — Bluechip Fund Rename

ICICI Prudential Bluechip Fund is now officially **ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund)** per the AMC site. TER CSV uses the exact name `ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund)`.

Scheme pages, KIM PDFs, and AMC investor/login UI URLs were excluded (non-textual or login-gated).

---

## Corpus registry

| # | Source name | `source_type` | `scheme_name` | `authority_level` | URL |
|---|-------------|---------------|---------------|-------------------|-----|
| 1 | ICICI Pru Large Cap — digital factsheet | `factsheet` | ICICI Prudential Large Cap Fund | factsheet | https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-large-cap-fund.php |
| 2 | AMC combined monthly factsheet PDF (Mar 2026) | `factsheet` | *(multi-scheme)* | factsheet | https://digitalfactsheet.icicipruamc.com/fact/pdf/fund-factsheet-for-march-2026.pdf |
| 3 | ICICI Pru Flexicap — digital factsheet | `factsheet` | ICICI Prudential Flexicap Fund | factsheet | https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-flexicap-fund.php |
| 4 | ICICI Pru ELSS Tax Saver — digital factsheet | `factsheet` | ICICI Prudential ELSS Tax Saver Fund | factsheet | https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-elss-tax-saver-fund.php |
| 5 | ICICI Pru Balanced Advantage — digital factsheet | `factsheet` | ICICI Prudential Balanced Advantage Fund | factsheet | https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-balanced-advantage-fund.php |
| 6 | AMFI — Introduction to Mutual Funds | `AMFI` | — | amfi | https://www.amfiindia.com/investor/knowledge-center-info?zoneName=IntroductionMutualFunds |
| 7 | AMFI — Investor Corner hub | `AMFI` | — | amfi | https://www.amfiindia.com/investor |
| 8 | SEBI — Investor Charter | `SEBI` | — | sebi | https://investor.sebi.gov.in/Investor-charter.html |
| 9 | ICICI Bank — MF FAQs (scheme & tax guidance) | `AMC_page` | — | amc_knowledge_centre | corpus:icici-bank-faqs-jun2026 |
| 10 | ICICI Pru — TER Jun 2026 — Large Cap | `factsheet` | ICICI Prudential Large Cap Fund | factsheet | corpus:ter-jun2026-large-cap |
| 11 | ICICI Pru — TER Jun 2026 — Flexicap | `factsheet` | ICICI Prudential Flexicap Fund | factsheet | corpus:ter-jun2026-flexicap |
| 12 | ICICI Pru — TER Jun 2026 — ELSS Tax Saver | `factsheet` | ICICI Prudential ELSS Tax Saver Fund | factsheet | corpus:ter-jun2026-elss |
| 13 | ICICI Pru — TER Jun 2026 — Balanced Advantage | `factsheet` | ICICI Prudential Balanced Advantage Fund | factsheet | corpus:ter-jun2026-balanced-advantage |

**Local files** (paths relative to project root; not fetched over HTTP):

| Corpus ID | File |
|-----------|------|
| `corpus:icici-bank-faqs-jun2026` | `corpus/FAQs.md` — sections split by embedded **Citation link** URLs (ICICI Bank / AMC) |
| `corpus:ter-jun2026-*` | `corpus/TotalExpenseRatioJun2026.csv` — one chunk per in-scope scheme, **latest date** in file |

**TER CSV scheme name map** (canonical → CSV `Scheme Name` column):

| Canonical `scheme_name` | CSV `Scheme Name` |
|-------------------------|-------------------|
| ICICI Prudential Large Cap Fund | ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund) |
| ICICI Prudential Flexicap Fund | ICICI Prudential Flexicap Fund |
| ICICI Prudential ELSS Tax Saver Fund | ICICI Prudential ELSS Tax Saver Fund |
| ICICI Prudential Balanced Advantage Fund | ICICI Prudential Balanced Advantage Fund |

### Authoritative redirects (not ingested; used in refusal templates)

| Source | URL | Use |
|--------|-----|-----|
| SEBI SCORES grievance portal | https://scores.sebi.gov.in | Regulatory redirects, learnings footer |
| CAMS — Capital Gain & Loss Statement | https://www.camsonline.com/Investors/Statements/Capital-Gain&Capital-Loss-statement | Registrar fallback for statements |
| CAMS — Statements hub | https://www.camsonline.com/Investors/Statements | Registrar fallback for statements |

---

## Sources explicitly avoided

Value Research, Morningstar, Fincash, Groww, Dezerv, Bajaj Finserv, ClearTax, Tax2win, Quora, and similar aggregator/blog content — only official AMC, AMFI, SEBI, and CAMS URLs are used.
