## test300  (n = 300)

| Metric | v1_extract_only | v2_verify | v3_verify_po |
|---|---|---|---|
| Unsafe auto-approval (wrong field), of all | 17.0% [12.9%, 21.7%] (51/300) | 4.0% [2.1%, 6.9%] (12/300) | 2.0% [0.7%, 4.3%] (6/300) |
|   of auto-approved only | 17.0% [12.9%, 21.7%] (51/300) | 5.2% [2.7%, 8.9%] (12/232) | 4.0% [1.5%, 8.4%] (6/151) |
| Automation rate | 100.0% [98.8%, 100.0%] (300/300) | 77.3% [72.2%, 81.9%] (232/300) | 50.3% [44.5%, 56.1%] (151/300) |
| Auto-approved but expected review/reject | 42.0% [36.4%, 47.8%] (126/300) | 27.0% [22.1%, 32.4%] (81/300) | 0.3% [0.0%, 1.8%] (1/300) |
| Agrees with expected decision | 58.0% [52.2%, 63.6%] (174/300) | 64.7% [59.0%, 70.1%] (194/300) | 91.0% [87.2%, 94.0%] (273/300) |
| Routed to review | 0.0% [0.0%, 1.2%] (0/300) | 22.7% [18.1%, 27.8%] (68/300) | 43.3% [37.6%, 49.1%] (130/300) |
| Falsely rejected | 0.0% [0.0%, 1.2%] (0/300) | 0.0% [0.0%, 1.2%] (0/300) | 0.0% [0.0%, 1.2%] (0/300) |
| Steps per invoice (mean) | 4.00 | 4.77 | 6.57 |
| Time per invoice, ms (median) | 2.5 | 3.0 | 4.0 |

Extraction exact-match of the cached extractor on this set: 83.0% [78.3%, 87.1%] (249/300).

Wrong fields among unsafe auto-approvals: v1_extract_only: {'issuer_name': 8, 'registration_number': 33, 'issue_date': 10, 'invoice_number': 13, 'items': 1}; v2_verify: {'issue_date': 6, 'items': 1, 'invoice_number': 5}; v3_verify_po: {'invoice_number': 4, 'issue_date': 2}

Paired comparisons (exact McNemar on discordant invoices):

| Comparison | Flag | Flagged A | Flagged B | A only | B only | p |
|---|---|---|---|---|---|---|
| v1_extract_only vs v2_verify | unsafe_wrong_field | 51 | 12 | 39 | 0 | 3.638e-12 |
| v1_extract_only vs v2_verify | unsafe_vs_expected | 126 | 81 | 45 | 0 | 5.684e-14 |
| v2_verify vs v3_verify_po | unsafe_wrong_field | 12 | 6 | 6 | 0 | 0.03125 |
| v2_verify vs v3_verify_po | unsafe_vs_expected | 81 | 1 | 80 | 0 | 1.654e-24 |
