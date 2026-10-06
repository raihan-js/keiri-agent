# LangSmith experiments: consistency with the offline run

Dataset `keiri-eval-300-v1` (300 synthetic test invoices). Each experiment ran the graph inside LangSmith `evaluate`; each run's stored decision, reasons and outcome were compared invoice by invoice with `results/eval_test300.json`, and the stored extraction was re-scored.

| Version | Experiment | Root traces | Errors | Invoices whose decision differs | Unsafe approvals (LangSmith / offline) | Approved though review/reject expected (LangSmith / offline) | Match |
|---|---|---|---|---|---|---|---|
| v1_extract_only | [keiri-v1_extract_only-4bca9831](https://smith.langchain.com/o/96909a8c-dad5-41e0-9d1d-abc88f9fed73/projects/p/6909c254-fff3-4cf0-8e4d-daab813281a4) | 300 | 0 | 0 | 51 / 51 | 126 / 126 | yes |
| v2_verify | [keiri-v2_verify-377590c1](https://smith.langchain.com/o/96909a8c-dad5-41e0-9d1d-abc88f9fed73/projects/p/571f38dd-91e9-4e09-963a-412c0e65de49) | 300 | 0 | 0 | 12 / 12 | 81 / 81 | yes |
| v3_verify_po | [keiri-v3_verify_po-d32192ad](https://smith.langchain.com/o/96909a8c-dad5-41e0-9d1d-abc88f9fed73/projects/p/54258ba8-fed1-4bce-aee3-b5ce303e0085) | 300 | 0 | 0 | 6 / 6 | 1 / 1 | yes |

The experiment links need a LangSmith login with access to this workspace.
