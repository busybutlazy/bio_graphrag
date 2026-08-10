## What & why

Adds the **third dispose outcome** to group Review — **記為 gap** (record-as-gap).

Until now a reviewer could only 核准 or 退回. But those two verbs cannot express the most interesting
case in a curated knowledge system: *the statement is probably right, and our schema simply cannot
represent it*. Turning that away as a "rejection" throws away exactly the signal that should drive
the schema forward. P3 already shipped a banner promising 「只能退回**或記為 gap**」 — with no button
behind it. This makes good on that promise and turns the seeded `demo_schema_gap` group into a
working end-to-end demo. Follows P1 (#10), P2 (#11), P3 (#12), P4 (#13).

## Changes

- **Backend:** `service.record_group_gap()` flips the group's `proposed` members to
  `status='schema_gap'` and appends exactly one `graph_change_logs` row (`action='schema_gap'`,
  `after_state={schema_gap_type, item_ids}`) — both inside **one transaction**, so a status flip can
  never exist without its audit row. Writes nothing to Neo4j.
- **API:** `POST /admin/review/groups/{group_id}/gap`, admin-gated, `{"error":{code,message}}`
  envelope. Guards: `404` unknown group · `409` no proposed members (incl. double-record) · `409` gate
  result ≠ `needs_schema_extension` (a *form* problem is a 退回, not a gap) · `422` blank reviewer or
  unknown `schema_gap_type`.
- **Taxonomy whitelist:** the 6 values from `docs/schema-gap-policy.md`. The reviewer picks a
  plain-language option; free text can never enter the audit semantics, which is what makes the gap
  record sortable later ("which extension unblocks the most rejected knowledge?").
- **Frontend:** the gap `<select>` + 記為 gap button render **only** for `needs_schema_extension`.
  All three actions disable together on click (a double-click cannot produce a duplicate audit row)
  and re-enable on failure — with 核准 still respecting the gate, so a failed call never opens a
  button the gate had closed.
- **Demo reset:** `make demo-reset` returns demo-origin `schema_gap` groups to `proposed` (audited),
  keeping the demo re-armable.
- **Docs:** `api_contract.md` documents the endpoint; `schema-gap-policy.md` corrected — its header
  claimed gaps land in `data/sample/expert_demo/schema_gap_backlog.json`, which was never true of
  this path.

## Also fixes: the Schema gate was enforced client-side only

While wiring the gate check, the same flaw surfaced in **`approve_group`**. The gap flag lives in
`curation_items.schema_check`, not in the node/edge payloads, so a proposal assembled by
`_proposal_from_items` alone evaluated as `pass`:

```
approve_group sees (no flag): pass
queue/UI + gap endpoint see : needs_schema_extension
```

That means the API **approved groups the queue and the UI both showed as 需補 schema, writing them
into the approved graph** — the only thing stopping it was a disabled frontend button. This
contradicts the enforcing-gate property asserted by `test_approve_refuses_when_schema_gate_fails`.

The flag lookup is now the shared `_group_possible_schema_gap()` helper, applied on every path that
evaluates a group's gate. The new regression test fails against the pre-fix code with
`DID NOT RAISE`, so it pins the behaviour rather than restating it.

This was outside the approved plan's scope (its stop conditions list "changes to approve/reject"), so
it was raised for a decision rather than folded in silently; the owner approved including it.

## Review & verification

Plan revision 2, executed one task at a time with a human checkpoint after the backend task.

- `make test` → **170 passed** (P4 baseline 163 + 7 new), run **online** with a live OpenAI key
  (real embeddings, not the lexical fallback).
- ruff 0.15.21 check + format clean · mypy clean (77 files) · `node --check` OK.
- **Owner browser pass, 4/4 scenarios**, each corroborated in Postgres rather than by eyeballing the
  page: one audit row per record with items and audit sharing a timestamp to the microsecond (proving
  the single transaction); a stale second tab refused with `409` having written **nothing**; `0` rows
  in Neo4j for the proposed ids.
- Live round trip: record → group leaves the queue → `make demo-reset` → group returns.

Full detail in `changes/group-review-gap-outcome/` (plan, task log, verification, change report).

## Known limitations (disclosed, deliberate)

- **No backlog view.** A recorded gap is auditable but not visible in any UI — it lives only in
  `graph_change_logs` rows and needs SQL to read. Backlog *management* (accumulate, sort,
  accept/reject a gap, `proposed_schema_change`) is a separate later change.
- `data/sample/expert_demo/schema_gap_backlog.json` remains orphaned legacy sample data;
  `schema-gap-policy.md` now says so explicitly.
- Gap eligibility is fixed to `needs_schema_extension` (decision D2) — not offered for `pass` or
  `fail_*` groups.

## Raised for a future change

- **Structured gap expression.** Letting the expert draw `節點 —(新關係)→ 節點` instead of picking a
  category covers gaps that are a missing edge type, but not the demo's own case (thyroxine
  modulating adrenaline's effect on metabolic rate) — there the target is another *effect*, which the
  schema reifies as a `RegulatoryEffect` node. Selecting it would require the expert to think in
  schema-modelling terms, which the expert lens deliberately hides. A design question, deferred.
- **Node dropdowns on the hand-made builder.** In 收錄 → 手工建立, edge source/target are still
  free-text identifier inputs while relation type is already a dropdown. Propose side, so out of
  scope here.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
