# Review Report: two-gate-review-p2 (rejection + gap groups, D5 third back-translation outcome)

## Review Context

- **Diff base and scope:** the **uncommitted worktree** on `main` (Phase 1 merged via PR #10 at
  `a7c6849`; baseline for P2 is `fc3d579`). P2 is 7 tracked files, +310/−13, plus the
  `changes/two-gate-review-p2/` artifacts. Nothing is committed yet — this review is of working-tree
  state.
- **Artifacts reviewed:** `IMPLEMENTATION_PLAN.md` (rev 1, Approved 2026-07-24), `TASK_LOG.md`,
  `VERIFICATION_REPORT.md`; the full worktree diff; new unit/integration tests; the seed
  `review_groups.json`; and live read-only probes of the running stack (`GET /admin/review/groups`
  with per-check inspection, `GET /nodes/<id>` collision probes).
- **Independence:** separate session from the implementation; I did not author the plan or code.
  Adequate. Shared-repo blind spots remain possible.
- **Evidence gaps:** **no `CHANGE_REPORT.md`** for P2 (`report-change` skipped again, as in Phase 1);
  the completion claim was assessed against the commit-less `VERIFICATION_REPORT.md` + plan.
- **Worktree note:** `docs/agent-guideline.md` — the dangling Phase-1 modification — is now committed
  (`fc3d579`), so that prior residual is resolved. The only uncommitted state is P2 itself, expected.
- **Verification independently reproduced:** I rebuilt the backend and ran the P2-affected suites —
  `test_back_translation`, `test_engineer_gate`, `test_review_groups`, `test_review`,
  `test_expert_demo` (**37 passed**) and `test_gold_examples` (**6 passed**). I did not re-run the full
  `make test`; the report's "153 passed, 1 failed" and the known idempotent flake are consistent with
  Phase 1 and with the affected-suite result, and the flake argument (P2 touches no chunk pipeline)
  holds.

## Completion Claim Assessment

Claim (`VERIFICATION_REPORT.md`): the Review queue now demonstrates **all four gate outcomes on real,
non-colliding data** (A2/A4), D5 splits the false-gap into flagged-gap vs plain-summary (A1), the
enforcing gate holds (A3), and the 7-case regression is intact.

**The functional core of the claim holds and I reproduced it live:**

```
GET /admin/review/groups
  demo_cortisol_blood_glucose  → pass                    使Blood glucose上升 (P1)
  demo_reject_form             → fail_pattern            plain summary (缺 ON_VARIABLE)
  demo_reject_meaning          → pass                    使Blood glucose上升 (P1, but reversed biology)
  demo_schema_gap              → needs_schema_extension  系統目前無法…表達 (P5, flagged)
GET /nodes/{cortisol,somatostatin,thyroxine,insulin_increases_blood_glucose} → 404 pre-approval
```

Four distinct outcomes, no id collisions, D5 renderer split verified, gate enforcing on
fail_pattern/gap. Good.

**But two things the claim does not surface turn up under inspection**, both consequences of how D5
was wired: (1) the gate's *per-check* display now contradicts itself on incomplete-pattern proposals,
and (2) the deliberately-approvable "meaning-reject" group writes wrong biology onto the flagship
concepts through an open-by-default surface, reversible only by hand. Neither breaks a test — the
tests assert overall `result`, not the check details or the operational blast radius — which is
exactly why they warrant a finding.

**Verdict: the feature works and demonstrates what P2 set out to demonstrate; the completion claim is
accurate as far as it goes, but under-discloses a gate-display regression and an operational footgun
that ride along with the design.**

## Findings

### High

**H1 — The "meaning-reject" demo group is approvable by design and, if approved, writes contradictory
wrong biology onto the flagship insulin / blood-glucose concepts in student-facing retrieval — on an
open-by-default admin surface, reversible only by manual curation.**

- *Evidence:* `data/sample/expert_demo/review_groups.json` → `group:demo_reject_meaning` proposes a
  new `regulatory_effect:insulin_increases_blood_glucose` (biologically reversed) with edges
  `hormone:insulin —HAS_EFFECT→ …_increases… —ON_VARIABLE/INCREASES→ physiological_variable:blood_glucose`.
  Live: the wrong RE is 404 (unapproved), but `hormone:insulin` and `physiological_variable:blood_glucose`
  are **200 (real, approved)**. The schema gate returns **`pass`** (confirmed live), so
  `approve_group` does **not** refuse it — the B1 collision guard only checks *member* ids
  (all new here), and the gate cannot detect reversed direction.
- *Impact:* approving it (which the UI 核准 button permits, since gate=pass) adds a second, opposite
  approved `RegulatoryEffect` for insulin wired into the *real* `blood_glucose` node. Student
  retrieval on the flagship concept would then surface `insulin decreases blood glucose` **and**
  `insulin increases blood glucose` as approved facts. Reversal requires manual
  `delete-node`/`delete-edge` (→ deprecated); **`make seed` does not remove it** (the wrong RE isn't
  in the seed graph, so re-seed leaves it). Per CLAUDE.md the admin surface is **open when
  `ADMIN_API_KEYS` is empty** (the documented demo default), and the site is served publicly at
  `biograph.busybutlazy.com` — so any visitor can approve wrong biology into the core retrieval path.
- *Nuance:* this is *pedagogically intended* — the demo's thesis is that the schema gate can't catch
  reversed biology and the human expert must reject it. The finding is not "remove it"; it is that the
  hazard is **under-guarded and hard to reset** for a live, open, portfolio-facing instance, and the
  blast radius is the flagship concept rather than an isolated demo island. `VERIFICATION_REPORT.md`
  raises the reversibility question but leaves it open; this closes it: not cleanly reversible.
- *Bounded remediation (human decides):* pick one — (a) confirm the public instance sets
  `ADMIN_API_KEYS` so approval isn't anonymous; (b) point the wrong RE at a throwaway demo variable
  instead of the real `physiological_variable:blood_glucose`, so an accidental approve can't touch
  flagship retrieval; (c) ship a one-command demo reset (deprecate demo-origin approved nodes) and
  document it; or (d) tag demo-reject approvals so they're excluded from student retrieval. Scope/design
  call — not the reviewer's.

### Medium

**M1 — Gate per-check regression: `testability` and `back_translation_available` now light green for
incomplete-pattern proposals, contradicting `pattern_validation` in the same panel.**

- *Evidence (live, `group:demo_reject_form`):*
  ```
  pattern_validation          ✕  RegulatoryEffect …somatostatin… 缺 ON_VARIABLE 出邊
  back_translation_available  ✓  本提案描述了體抑素…請就內容本身審查。
  testability                 ✓  可導出最小斷言
  ```
  `engineer_gate.py:124-138` sets both `back_translation_available` and `testability` to
  `not rendered["is_gap"]`. Before D5, a no-pattern/incomplete proposal had `is_gap=True`, so both
  correctly showed ✕. After D5 (`back_translation.py:132-150`), an *unflagged* no-pattern proposal is
  a plain summary with `is_gap=False`, so both flip to ✓ — including **`testability: 可導出最小斷言`
  ("a minimal assertion can be derived")** for a `RegulatoryEffect` that has *no direction and no
  `ON_VARIABLE`*, from which nothing can be derived.
- *Impact:* the Schema-gate tab is a showcase of "every check is really computed, not canned." It now
  displays a self-contradictory verdict on the P2 form-reject demo (pattern incomplete, yet testable),
  and the same flip hits `cases.json` case 6 in the standalone expert-demo gate tab. The overall
  `result` correctly stays `fail_pattern` (`_decide` prioritizes it), so **approval is still blocked —
  this is a display/soundness defect, not a safety hole.** But it directly undercuts the change's own
  narrative ("tell schema-valid-but-unusual from inexpressible"): an incomplete pattern is neither, and
  the gate now mislabels it as testable.
- *Test gap:* `test_d5_unflagged_no_pattern_passes_gate` asserts `result == "pass"` but never inspects
  the `testability` / `back_translation_available` check details, so the regression is unguarded.
- *Bounded remediation:* decouple `testability` (and arguably `back_translation_available`) from
  `is_gap`. Testability should key on "a known regulatory pattern (P1–P4) was matched," not on "the
  renderer produced any non-gap sentence." A plain P0 summary should leave `testability` ✕ with "無
  pattern,不導斷言" while `back_translation_available` can legitimately pass.

**M2 — The merged Review screen lacks the expert-demo screen's M1 guard, so a form-rejected group now
shows a "系統理解" sentence in the 專家審閱 tab; the report's "M1 concern does not recur" is only
half-substantiated.**

- *Evidence:* `frontend/app.js` — `renderExpertDemo.paintExpert` returns early for
  `fail_schema|fail_pattern|fail_testability` with "依流程不進入專家審查…" and **suppresses**
  `system_understanding` (the original M1 fix). `renderReview.paintExpert` (the merged surface) has
  **no such guard** — it unconditionally renders `系統理解` + concept map + actions. P2 newly seeds a
  `fail_pattern` group (`demo_reject_form`) into *this* queue, so for the first time the review screen
  will show a system-understanding sentence ("本提案描述了…請就內容本身審查。") for a proposal the
  gate rejected on form.
- *Impact:* the false *gap* text is indeed gone (D5's real win), so it's not the old M1 bug. But a
  form-rejected proposal still gets a plain-language "system understanding" in the expert tab, while
  the sibling screen deliberately hides it — an inconsistency, and arguably still the "don't narrate
  understanding for a form-rejected proposal" principle M1 encoded. `TASK_LOG.md` T4 asserts "D5
  removed the false-gap so the M1 concern does not recur in the merged view"; that is only partly true.
- *Not browser-verified:* both screens are manual-only; `VERIFICATION_REPORT.md` marks the frontend
  **PENDING a human browser check**, and no such check is recorded for P2. So M2 is reasoned from code,
  not observed.
- *Bounded remediation:* either apply the same fail-gate guard in `renderReview.paintExpert`, or make a
  deliberate decision that the merged screen *should* show the plain summary (with the disabled 核准 +
  "只能退回" message as the guardrail) and record it, so the two screens' divergence is intentional
  rather than accidental.

### Low

**L1 — Post-D5 the engineer gate can no longer auto-detect a schema gap; the boundary now rests
entirely on a hand-set `possible_schema_gap` flag.** Before D5, any no-pattern proposal → `needs_schema_extension`
(over-flagging, but self-driven). After D5, an unflagged no-pattern proposal — *including a zero-edge
bag of disconnected nodes* — passes the full gate (pattern ✓, testability ✓) and is approvable; only a
seed/proposer-set flag produces `needs_schema_extension`. This is the **approved** D5 tradeoff (fewer
false gaps), so not a defect — but the governance consequence is worth stating: the gate's ability to
*discover* an inexpressible phenomenon is gone; gaps are now self-declared, and a real gap that nobody
flags will sail through as `pass`. Relevant when P3 (hand-made) and P5 (real-extract) groups arrive
without a curator setting the flag.

**L2 — `schema_check` JSONB is reused to carry the gap hint (`group_possible_schema_gap`).**
`stage_demo_review_group` merges a *seed hint* into the column meant for `schema_checker` *computed
output* (`load_postgres.py`), and `list_groups` reads it back. Functionally fine and null-safe
(`(_load_json(...) or {})`), and it is the **approved** no-migration choice (plan R3), but it conflates
provenance: a consumer of `schema_check` can no longer assume every key came from the schema checker.
The `group_meta` column remains the clean upgrade if this generalizes. Noted, not blocking.

### Suggestion

- **S1 — No `CHANGE_REPORT.md` for P2** (same gap as Phase 1). `report-change` gives the diff-vs-plan
  deviation disclosure that a verification report isn't structured to; worth running before commit.
- **S2 — The plain-summary (P0) render path is not exercised by any of the four demo groups in the
  UI** (disclosed in the report): `demo_reject_meaning` passes via a real P1 pattern, `demo_reject_form`
  is fail_pattern (gate tab), `demo_schema_gap` is a flagged gap. So the marquee D5 outcome — a
  schema-valid, no-pattern, *approvable* plain summary — has unit/integration coverage but **no live
  demo group** and no browser confirmation. Consider one seed group that lands on P0/pass, so the demo
  actually shows the third outcome it was built for.

## Requirement and Test Coverage Gaps

| # | Claimed | Assessed |
|---|---|---|
| A1 | Renderer: flagged→gap, unflagged→plain summary, P1–P4 unchanged | **Confirmed** (unit tests + live; gold + expert_demo green) |
| A2 | Queue lists 4 outcomes | **Confirmed live** (pass / fail_pattern / pass / needs_schema_extension) |
| A3 | Enforcing gate: form-reject/gap → 409, cortisol → 200 | **Confirmed** for form-reject/gap. Caveat: `demo_reject_meaning` is `pass` → *approvable*; that's intended, but see H1 for the consequence |
| A4 | No collision — every proposed id 404 pre-approval | **Confirmed live** (4×404) |
| A5 | `make test` green except known flake; ruff/format/mypy clean | Affected suites reproduced green (43); full count + ruff/mypy taken from the report, not re-run here |
| D5-gate | unflagged→pass, flagged→needs_schema_extension | Confirmed — **but** the per-check lights that produce "pass" are themselves wrong for incomplete patterns (M1) |

Unguarded by tests: the `testability`/`back_translation_available` check *content* on incomplete-pattern
proposals (M1); the review-screen expert-tab render for a fail_pattern group (M2); any frontend behavior.

## Compatibility, Security, and Scope Assessment

- **Migration:** none — the approved no-migration `schema_check` reuse (L2). Backward-compatible.
- **Contract:** endpoint shapes unchanged; an `understanding` may now be a plain summary rather than a
  gap. No breaking change.
- **Shared-function blast radius:** `back_translation.render_understanding` is used by *both* the review
  service and the live expert-demo screen. The 7-case regression (gold + expert_demo suites) passes, and
  case 6's changed understanding is suppressed by the expert-demo M1 guard — so no *observable*
  regression on that screen. The regression that *does* surface is M1 (gate check lights) and M2 (review
  screen), both correctly downstream of the same coupling.
- **Security:** no new endpoints, deps, or secrets; admin gating unchanged. The H1 exposure is
  authorization-model-dependent (open admin = anonymous approve) — a deployment/config concern, not a
  code injection. `load_neo4j._safe_type` still guards label interpolation.
- **Scope:** stays within the plan's approved paths; no P3–P5 leakage; `frontend/app.js` correctly
  untouched (T4 was no-change). No out-of-scope edits, no generated artifacts.
- **Rollback:** clean (revert renderer split, seed groups, flag threading; no migration). Caveat
  inherited from H1: an *approved* meaning-reject group is not rolled back by revert or re-seed — only by
  curation delete.

## Unreviewed Areas and Residual Risk

- **Frontend not executed.** M2 is reasoned from code; the four-outcome click-through (esp. the disabled
  核准 on form-reject/gap, and the meaning-reject that passes the gate but should be rejected) is the one
  unexecuted surface, and the report marks it PENDING. A human browser pass is still owed.
- **Full `make test` not re-run here** (affected suites reproduced green). The "153 passed" total and
  ruff/format/mypy cleanliness are taken from the verification report.
- **I did not execute any approval** against the live graph — H1's blast radius is established from the
  gate result (`pass`), the real-node 200s, the new-node 404s, and MERGE/seed semantics, not from an
  observed mutation. A human can confirm in seconds on a throwaway volume.
- Absence of further findings is not proof of correctness. The through-line of H1/M1/M2/L1 is one design
  fact: **D5 moved judgment the gate used to make (over-cautiously) onto humans and flags.** That is a
  legitimate, approved direction — the residual risk is that the surrounding UI and check-lights haven't
  fully caught up to it, and the operational guardrails for the now-approvable wrong-biology case are
  thin.

## Human Disposition Required

H1 (guardrails/reset for the approvable wrong-biology demo on an open surface) and the M2 decision
(should the merged review screen show understanding for a form-rejected group, or guard it like the
expert-demo screen?) are **design/scope calls, not reviewer calls**. M1 is a bounded code fix
(decouple `testability` from `is_gap`) but whether to take it now or log it is the human's.

The reviewer does not approve, fix, merge, or release this change.

---

## Re-review — remediation pass (2026-07-24, uncommitted worktree)

Re-ran against the P2 remediation (still uncommitted; adds `engineer_gate.py`, `frontend/app.js`,
`scripts/reset_demo_review.py`, `Makefile`, seed + test changes). Independence unchanged (separate
session from implementation and fix). I read the full remediation diff, rebuilt the backend, ran the
affected suites, and exercised the live stack including a full approve→reset round-trip. My
`REVIEW_REPORT.md` shipped intact — not edited to soften findings.

### Disposition of each finding

| # | Finding | Status | Evidence |
|---|---|---|---|
| **H1** | Meaning-reject approvable → wrong biology onto flagship concepts, hard to reset | **Fixed (isolate + reset), verified end-to-end** | Group is now fully demo-namespaced (`hormone:demo_insulin`, `physiological_variable:demo_blood_glucose`, `regulatory_effect:demo_insulin_increases_blood_glucose`); labels still 胰島素/血糖 so teaching is unchanged. Live: approved the group → 200; **real `hormone:insulin` neighbors contain zero demo nodes** (no bleed); real `blood_glucose` 200 / `demo_blood_glucose` 404. `make demo-reset` deleted 3 nodes + 3 edges, re-queued 6 items; demo RE → 404, group re-listed. The correct additions (cortisol, plain-addition) still reference the real graph — isolation is applied *only* to the deliberately-wrong group, which is exactly right. |
| **M1** | `testability` green while `pattern_validation` red | **Fixed, verified live** | `engineer_gate.py:133` now `testable = not is_gap AND pattern_detail is None`, with a distinct "pattern 不完整,不導斷言" message. Live `demo_reject_form`: `pattern:False, testability:False` (was the contradiction). Regression test `test_incomplete_pattern_is_not_testable` asserts both are False. |
| **M2** | Review screen lacks expert-demo's fail-gate guard | **Resolved as a deliberate, recorded divergence** | `renderReview.paintExpert` now shows a banner ("未通過 Schema gate…只能退回" / "schema gap…只能退回或記為 gap") above the honest post-D5 summary, with 核准 disabled — chosen over hiding, and documented in the code comment + CHANGE_REPORT. This is the "decide and record" remediation M2 asked for. **Not browser-verified** — still code-only. |
| **L1** | Gate can't auto-detect gaps (self-declared now) | Acknowledged, no change | Approved D5 tradeoff; documented. |
| **L2** | `schema_check` reuse conflates provenance | Acknowledged, no change | Approved no-migration choice; `group_meta` remains the upgrade path. |
| **S1** | No CHANGE_REPORT | **Fixed** | `CHANGE_REPORT.md` added. |
| **S2** | P0 plain-summary outcome not demoed live | **Fixed** | `group:demo_plain_addition` (胰島 PART_OF 胰臟) added; live `pass` + plain summary + approvable — the third outcome now shows in the queue. |
| — | Seed convergence bug (found during their verification) | **Fixed** | `stage_demo_review_groups` now deletes all still-`proposed` demo items before re-staging, so *content* edits to a group take effect (the old `ON CONFLICT DO NOTHING` kept stale items). Verified: 5 groups seed cleanly with correct per-group results. |

### Verified independently this pass
- Affected suites (`test_back_translation`, `test_engineer_gate`, `test_review_groups`, `test_review`,
  `test_expert_demo`, `test_gold_examples`) → **44 passed** after rebuild. The report's full
  "154 passed, 1 failed" (the known idempotent flake) is consistent; I did not re-run the 4-min suite.
- Live 5-outcome queue; M1 fix; H1 isolation (no bleed) + `make demo-reset` round-trip.

### New / residual (all Low — disclosed, none blocking)
- **The reset script hard-deletes approved graph nodes without a `graph_change_logs` row**, and uses
  raw `DETACH DELETE` rather than the curation `delete_node` (→ `deprecated` + audit). It's a
  demo-maintenance utility touching only `proposed_by='demo'` data, but for a project whose thesis is
  *auditable* governance, a graph mutation that skips the audit trail is slightly off-thesis. Consider
  routing it through the curation delete path, or at least appending an audit row. Not blocking.
- **P0 plain summaries with no pattern at all** (e.g. `demo_plain_addition`) still show
  `testability: True`. The M1 fix correctly targets the *contradiction* (incomplete pattern); a
  complete structural `PART_OF` reading as testable is defensible, not self-contradictory — so this is
  a judgment call left as-is, not a regression.
- **Frontend remains manual-only and un-browsed this phase** — the M2 banner and the H1 isolation
  labels (demo nodes labelled 胰島素/血糖) need a human pass; a mislabel there would be invisible to
  the API tests.
- Still an **uncommitted worktree**; `docs/agent-guideline.md` correctly left unstaged.

### Re-review verdict

**Every High and Medium finding is resolved, and H1 — the one with real blast radius — is fixed *and*
independently verified end-to-end (isolation proven by no-bleed, reset proven by round-trip).** The
remediation is well-targeted: it quarantined only the deliberately-wrong group while letting the
correct demos still exercise the real graph, and it fixed a latent seed-convergence bug its own
verification surfaced. The two open items (M2 browser check, reset-script audit trail) are honestly
disclosed and non-blocking for a Phase-2 demo slice.

Remaining disposition is the human's: accept with the disclosed browser pass owed, and optionally take
the reset-script audit-trail suggestion. The reviewer still does not approve, merge, or release.
