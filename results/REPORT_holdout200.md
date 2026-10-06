## holdout200  (n = 200)

| Metric | v1_extract_only | v2_verify | v3_verify_po |
|---|---|---|---|
| Unsafe auto-approval (wrong field), of all | 48.5% [41.4%, 55.7%] (97/200) | 9.0% [5.4%, 13.9%] (18/200) | 0.5% [0.0%, 2.8%] (1/200) |
|   of auto-approved only | 48.5% [41.4%, 55.7%] (97/200) | 17.1% [10.5%, 25.7%] (18/105) | 1.6% [0.0%, 8.4%] (1/64) |
| Automation rate | 100.0% [98.2%, 100.0%] (200/200) | 52.5% [45.3%, 59.6%] (105/200) | 32.0% [25.6%, 38.9%] (64/200) |
| Auto-approved but expected review/reject | 37.5% [30.8%, 44.6%] (75/200) | 15.0% [10.4%, 20.7%] (30/200) | 0.0% [0.0%, 1.8%] (0/200) |
| Agrees with expected decision | 62.5% [55.4%, 69.2%] (125/200) | 58.0% [50.8%, 64.9%] (116/200) | 68.5% [61.6%, 74.9%] (137/200) |
| Routed to review | 0.0% [0.0%, 1.8%] (0/200) | 47.5% [40.4%, 54.7%] (95/200) | 62.5% [55.4%, 69.2%] (125/200) |
| Falsely rejected | 0.0% [0.0%, 1.8%] (0/200) | 0.0% [0.0%, 1.8%] (0/200) | 0.0% [0.0%, 1.8%] (0/200) |
| Steps per invoice (mean) | 4.00 | 4.53 | 6.38 |
| Time per invoice, ms (median) | 2.5 | 2.9 | 3.8 |

Extraction exact-match of the cached extractor on this set: 51.5% [44.3%, 58.6%] (103/200).

Wrong fields among unsafe auto-approvals: v1_extract_only: {'items': 88, 'registration_number': 34, 'totals': 34, 'invoice_number': 7, 'grand_total': 4, 'issue_date': 18, 'tax_included': 2, 'issuer_name': 6, 'recipient_name': 1}; v2_verify: {'items': 17, 'issue_date': 3, 'invoice_number': 1}; v3_verify_po: {'issue_date': 1}

Paired comparisons (exact McNemar on discordant invoices):

| Comparison | Flag | Flagged A | Flagged B | A only | B only | p |
|---|---|---|---|---|---|---|
| v1_extract_only vs v2_verify | unsafe_wrong_field | 97 | 18 | 79 | 0 | 3.309e-24 |
| v1_extract_only vs v2_verify | unsafe_vs_expected | 75 | 30 | 45 | 0 | 5.684e-14 |
| v2_verify vs v3_verify_po | unsafe_wrong_field | 18 | 1 | 17 | 0 | 1.526e-05 |
| v2_verify vs v3_verify_po | unsafe_vs_expected | 30 | 0 | 30 | 0 | 1.863e-09 |
