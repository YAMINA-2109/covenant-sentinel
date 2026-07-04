# Demo fixtures

Synthetic documents authored during the hackathon for reproducible demos. Two cases: **ACME** (stressed borrower — engineered so the agent must demonstrate every behaviour the Vultr track brief asks for) and **Globex** (healthy borrower — proves the agent also says "compliant" when everything is fine). PDF versions of the ACME case live in `pdf/` (same content, typeset as lender-file documents; regenerate with `backend/scripts/make_pdf_fixtures.py`). A fully verified reference run is frozen in `golden_trace_acme.json` (events + final state).

## Case 2 — Globex Manufacturing GmbH (healthy)

`globex_facilities_agreement.txt` + `globex_q2_2026_financial_report.txt` + `globex_treasury_pack_q2_2026.txt` — covenants ≤4.00x leverage / ≥ EUR 10m liquidity / ≥2.50x interest coverage. Expected: **3× OK at 100% confidence** (3.20x, EUR 14.8m, 2.78x), stable long-horizon trends, no false alarms. Run it with `python scripts/run_demo.py --globex`.

## Case 1 — the ACME scenario

## The three documents

| File | Plays the role of |
|---|---|
| `acme_credit_agreement.txt` | The credit agreement (covenants in Section 7.1, definitions in Section 1, supersession rule in Section 9.4, equity cure in Section 10.2) |
| `acme_q2_2026_financial_report.txt` | The borrower's Q2 2026 quarterly report (final figures, LTM reconciliation in Note 4) |
| `acme_treasury_pack_q2_2026.txt` | Treasury flash note (preliminary cash) + debt movement schedule (the "why") |

## What the agent should conclude

| Covenant (Section 7.1) | Required | Actual (Q2 2026) | Expected verdict |
|---|---|---|---|
| (a) Leverage Ratio | ≤ 3.50x | 370.0 / 100.0 = **3.70x** | **BREACH** — cause-matched: +EUR 45.0m debt in Q2, of which EUR 40.0m documented acquisition draw (Project Falcon) and EUR 5.0m with no documented purpose → cause coverage 40/45 ≈ 89% |
| (b) Minimum Liquidity | ≥ EUR 5.0m | flash 4.2m vs final **5.3m** | **OK — false positive eliminated**: the Critic applies Section 9.4 (final figures supersede preliminary flash) |
| (c) Interest Coverage | ≥ 2.00x | 100.0 / 40.0 = **2.50x** | **AT RISK** — passing today, but trending 3.10 → 2.80 → 2.50 (−0.30/quarter); projected to cross 2.00x around **Q4 2026** |

## Built-in traps (what separates an agent from basic RAG)

1. **LTM vs quarterly EBITDA** — the report headline shows quarterly EBITDA (EUR 25.0m → would give a nonsense 14.8x ratio). The covenant definition requires *LTM* EBITDA, which only appears in Note 4 → forces a targeted second retrieval.
2. **Preliminary vs final cash** — two conflicting cash figures exist (4.2m flash, 5.3m final). A naive system flags a breach; the Critic resolves the conflict with Section 9.4.
3. **Unexplained transaction** — EUR 5.0m of the debt jump has no documented purpose, so cause coverage is 89%, not 100% — the confidence score must honestly reflect that.
