# Rule: Broker PDCA & Zero-Contradiction (core)

Full version (PDCA entry format, examples): `docs/agent/full/broker_pdca_rca_full.md`.

- **Broker isolation** — Krungsri TradeMan, Click2Win, Liberator, Settrade Open API differ completely (session, 2FA, DOM). Never mix assumptions. Knowledge lives per broker in `rca/<broker>/` and `learned_workflows/<broker>/`.
- **PDCA log** — every fixed bug/edge case → RCA entry in that broker's file: ID+date (e.g. `KSS-RCA-001 (2026-09-29)`), Symptom, Root cause, Edge cases, Proven solution (code/selectors), User feedback.
- **Zero-contradiction** — when code/selectors/steps change, update the existing runbook in `learned_workflows/*.md` immediately.
- **Self-anneal first** — diagnose from snapshot (HTML/screenshot text), try fixes; beyond that, notify the user with the root cause.
