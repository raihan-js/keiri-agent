## val150  (n = 150)

| Metric | v1_extract_only | v2_verify | v3_verify_po |
|---|---|---|---|
| Unsafe auto-approval (wrong field), of all | 10.7% [6.2%, 16.7%] (16/150) | 0.0% [0.0%, 2.4%] (0/150) | 0.0% [0.0%, 2.4%] (0/150) |
|   of auto-approved only | 10.7% [6.2%, 16.7%] (16/150) | 0.0% [0.0%, 3.0%] (0/121) | 0.0% [0.0%, 4.6%] (0/79) |
| Automation rate | 100.0% [97.6%, 100.0%] (150/150) | 80.7% [73.4%, 86.7%] (121/150) | 52.7% [44.4%, 60.9%] (79/150) |
| Auto-approved but expected review/reject | 40.0% [32.1%, 48.3%] (60/150) | 28.0% [21.0%, 35.9%] (42/150) | 0.0% [0.0%, 2.4%] (0/150) |
| Agrees with expected decision | 60.0% [51.7%, 67.9%] (90/150) | 64.0% [55.8%, 71.7%] (96/150) | 92.0% [86.4%, 95.8%] (138/150) |
| Routed to review | 0.0% [0.0%, 2.4%] (0/150) | 19.3% [13.3%, 26.6%] (29/150) | 38.0% [30.2%, 46.3%] (57/150) |
| Falsely rejected | 0.0% [0.0%, 2.4%] (0/150) | 0.0% [0.0%, 2.4%] (0/150) | 0.0% [0.0%, 2.4%] (0/150) |
| Steps per invoice (mean) | 4.00 | 4.81 | 6.62 |
| Time per invoice, ms (median) | 2.5 | 3.0 | 3.8 |

Extraction exact-match of the cached extractor on this set: 89.3% [83.3%, 93.8%] (134/150).

Wrong fields among unsafe auto-approvals: v1_extract_only: {'issuer_name': 2, 'registration_number': 14, 'invoice_number': 6, 'issue_date': 3}; v2_verify: none; v3_verify_po: none

Paired comparisons (exact McNemar on discordant invoices):

| Comparison | Flag | Flagged A | Flagged B | A only | B only | p |
|---|---|---|---|---|---|---|
| v1_extract_only vs v2_verify | unsafe_wrong_field | 16 | 0 | 16 | 0 | 3.052e-05 |
| v1_extract_only vs v2_verify | unsafe_vs_expected | 60 | 42 | 18 | 0 | 7.629e-06 |
| v2_verify vs v3_verify_po | unsafe_wrong_field | 0 | 0 | 0 | 0 | 1 |
| v2_verify vs v3_verify_po | unsafe_vs_expected | 42 | 0 | 42 | 0 | 4.547e-13 |
