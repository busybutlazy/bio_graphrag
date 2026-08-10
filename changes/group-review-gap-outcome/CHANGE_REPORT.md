# Change Report: group-review-gap-outcome

Branch `feat/group-review-gap-outcome`, based on `main` @ `da2eed2` (P4 merged as `705e61c`;
rebased after PR #14 repo/CI hardening). Plan revision 2, executed one task at a time (T1 → T2 → T3).
Task 1 committed as `ddaf281`; Tasks 2–3 in the working tree.

## Completed

Added the **third dispose outcome** to group Review — *record-as-gap*. When the Schema gate says
`needs_schema_extension`, the reviewer can record the group as a typed schema gap instead of only
approving or turning it away. This backs the P3 banner that already promised
「只能退回**或記為 gap**」 with no action behind it, and makes the seeded `demo_schema_gap` group a
working end-to-end demo.

- **Backend:** `service.record_group_gap()` — flips the group's `proposed` members to
  `status='schema_gap'` and appends exactly one `graph_change_logs` row (`action='schema_gap'`,
  `target_type='proposal_group'`, `after_state={schema_gap_type, item_ids}`), both inside a single
  `conn.transaction()`; writes nothing to Neo4j. Guards: 404 unknown group, 409 no proposed members,
  409 gate result ≠ `needs_schema_extension`, 422 blank reviewer / unknown `schema_gap_type`.
- **API:** `POST /admin/review/groups/{group_id}/gap` + `SchemaGapRequest`, admin-gated, error
  envelope `{"error":{code,message}}` like the other group routes.
- **Taxonomy whitelist:** `VALID_SCHEMA_GAP_TYPES` (6 values from `docs/schema-gap-policy.md`), so
  free text can never enter the audit semantics.
- **Demo reset:** `make demo-reset` also returns demo-origin `schema_gap` items to `proposed`, one
  audit row per group (`action='reset'`), keeping the demo re-armable.
- **Frontend:** re-added `GAP_OPTIONS`; `reviewActions` renders a gap-type `<select>` + 記為 gap
  button **only** for `needs_schema_extension`. All three actions disable together on click (a
  double-click cannot fire two requests) and re-enable on failure. `?v=20260810-1` bumped on both
  `app.js` and `styles.css`.
- **Docs:** `api_contract.md` documents the endpoint, its four guards, the taxonomy, the
  single-transaction property, and the absence of a backlog view. `schema-gap-policy.md` updated —
  its header still claimed gaps are written to `data/sample/expert_demo/schema_gap_backlog.json`,
  which was never true of this path.

## Deviations from the approved plan

1. **Gate flag was not threaded (in-scope fix, required).** `record_group_gap` as drafted evaluated
   the gate on `_proposal_from_items(proposed)` alone, but the `needs_schema_extension` verdict comes
   from `possible_schema_gap`, which `list_groups` injects from each item's
   `schema_check.group_possible_schema_gap`. Measured: `no flag → pass`, `with flag →
   needs_schema_extension`. The D2 guard would therefore have returned 409 for **every** genuine gap
   group — the feature could never have fired. Fixed by extracting `_group_possible_schema_gap()`
   from `list_groups` (behaviour there unchanged) and applying it in `record_group_gap`.

2. **`approve_group` had the same hole (scope extension, owner-approved 2026-08-10).** A group the
   queue and the UI both showed as `needs_schema_extension` evaluated as `pass` inside
   `approve_group`, so the API **approved it and wrote it into the graph** — the enforcing Schema
   gate was in practice enforced by a disabled frontend button, contradicting the property asserted
   by `test_approve_refuses_when_schema_gate_fails`. The plan's stop conditions list "changes to
   approve/reject", so this was raised rather than silently fixed; the owner approved folding it in.
   Fix = the same helper, plus `test_approve_refuses_a_flagged_schema_gap_group`, which fails
   (`DID NOT RAISE`) against the pre-fix code.

3. **Guard order.** `reviewer` and `schema_gap_type` are validated before opening the connection, so
   a bad payload on an unknown group returns 422 rather than the plan's 404. One fewer DB round-trip;
   tests assert the actual order.

4. **UI copy added beyond the plan.** The plan specified only a `<select>` + button. On review the
   owner (the project's domain expert) found the bare dropdown meaningless, so an instruction line
   was added, and the reason textarea's placeholder now explains that on a gap the free-text
   description is the substantive part (it lands verbatim in the audit row). No change to the
   taxonomy wording itself — that text remains verbatim from `docs/schema-gap-policy.md`.

## Not completed / deliberately excluded

- **No backlog view.** A recorded gap is auditable but not visible in any UI — it lives only in
  `graph_change_logs` rows and needs SQL to read. Backlog *management* (accumulate, sort,
  accept/reject a gap, `proposed_schema_change`) is Out of Scope per the plan and disclosed in
  `api_contract.md`.
- `data/sample/expert_demo/schema_gap_backlog.json` stays orphaned legacy sample data; a future
  backlog change decides its fate. `schema-gap-policy.md` now says so explicitly.
- Gap eligibility stays fixed to `needs_schema_extension` (D2). Not offered for `pass` / `fail_*`.
- Nothing else outstanding: the browser pass (condition 6) was completed by the owner, 4/4 scenarios,
  each cross-checked against Postgres — see `VERIFICATION_REPORT.md`.

## Raised for a future change (owner discussion, 2026-08-10)

- **Structured gap expression.** The owner proposed letting the expert express the gap as
  `節點 —(新關係)→ 節點` instead of picking a category. Analysis: it covers gaps that are a missing
  edge type between two concepts, but not the demo's actual case (thyroxine modulating adrenaline's
  effect on metabolic rate) — there the "target" is another *effect*, which the schema reifies as a
  `RegulatoryEffect` node. Selecting that node would require the expert to think in schema-modelling
  terms, which the expert lens deliberately hides. Deferred as a design question.
- **Node dropdowns on the hand-made builder.** In Ingestion → 手工建立, edge source/target are
  free-text identifier inputs (`hormone:insulin` typed by hand) while relation type is already a
  dropdown, with `+ 概念`/`+ 關係` and per-row `✕` already present. Replacing the two text inputs with
  node selectors is a real usability win — propose side, so out of scope here.

## Verification summary

`make test` **170 passed** (P4 baseline 163 + 7 new), online with a live key after the owner topped
up the account. ruff 0.15.21 check + format clean; mypy clean (77 files); `node --check` OK. Live
round trip through nginx: record → group leaves the queue → `make demo-reset` → group returns.
Full detail and commands in `VERIFICATION_REPORT.md`.
