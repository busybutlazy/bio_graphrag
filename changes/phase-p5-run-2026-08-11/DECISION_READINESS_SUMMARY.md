# Decision Readiness Summary

Status: Ready

## Decision Inventory Reference

`changes/phase-p5-run-2026-08-11/DECISION_INVENTORY.md`（2026-08-11，`main` @ `0a3e5be`）

## Resolved Decisions

- **G1 分組規則 = pattern instance 切分。** 每個 `RegulatoryEffect` / `Interaction` 實例連同其必要邊
  與端點節點成一組；殘餘每 chunk 一組。由確定性的 `_pattern_check` 語意實作。
- **G2 去重語意 = 已 approved 只引用、未核准則各組重複提案。** item_id 改為群組範圍
  `curation:{group_id}:{elem_id}`。接受「後核准者命中 409 需退回重提」的後果。
- **G3 分組限縮在單一 chunk 內。** `runner.py` 逐 chunk 迴圈結構不變；被切斷的 pattern 由 Schema gate
  判 `fail_pattern` 而退回。
- **G4 P5 拆分。** 本次只交付抽取路徑分組。

## Implementation-Owned Defaults

- **I1** `group_id` 確定性命名（`group:llm:{chunk_id}:{anchor}` / `…:residual`）——保住重跑冪等性，
  否則群組範圍 item_id 會讓重跑灌爆審閱佇列。需補 `curation_items` 層級的冪等斷言。
- **I2** 無殘餘元素則不產生殘餘組。已知後果：4-chunk 章節約產生 6–8 個待審群組。
- **I3** 以 `runner.py` 既有 Neo4j driver 判定 approved，不新增資料來源。
- **I4** 不做 backfill／migration（DB 內無未分組 llm 資料）。
- **I5** 抽取路徑不設 `possible_schema_gap`（schema 無此欄位，改由專家審閱時判定）。

## Intentionally Deferred Decisions

- Decision: schema-gap backlog 生命週期（accept／reject／復原、engineer override、孤兒 JSON 去留）
- Why Safe Now: 抽取分組的 implementation plan 可在不假設任何 backlog 答案下完整寫出；不改變本次
  scope、契約或驗收條件的意義
- Affected Scope: P5 的第二個產出，非本次
- Decision Owner: owner
- Becomes Blocking When: 開始對真實章節（非 demo 來源）記錄 gap 時，或宣告 P5 完成時

- Decision: gold 改打真實抽取輸出
- Why Safe Now: 現有 gold（6 tests，全綠）仍是有效的 renderer 回歸網，本次交付不依賴它
- Affected Scope: P5 的第一個產出的後半
- Decision Owner: owner
- Becomes Blocking When: 宣告 P5 完成時，或要以真實抽取輸出作為 golden 基準時

## Blocking Open Decisions

None

## Conflicts or Assumptions Found

- **實測推翻了兩個看似合理的選項。** 一個群組含兩個 pattern 時，`render_understanding` 只描述第一個
  （`back_translation.py:72` 取 `[0]`），而 Schema gate 仍回 `pass`。專家會在只讀到一半描述的情況下
  核准寫入。這淘汰了「一個 chunk 一組」，也淘汰了「連通元件」——本語料的兩個血糖陳述共用「血糖」節點，
  連通元件會把它們併成一組。此為本次會期最重要的發現，且**與現有測試無關**（沒有測試涵蓋多 pattern
  proposal 的 lens 行為）。
- **G2 與既有 guard 的交互作用是真實的，非理論。** 群組範圍 item_id + 共用未核准概念 →
  `approve_group` 的 B1 guard 會讓後核准的群組 409。這個後果已由 owner 明示接受，不是被忽略。
- **Roadmap 的延後條款觸發但決定從未做出。** `unified-two-gate-review:154` 寫明
  「real-extract grouping is deferred (becomes blocking when the real pipeline lands)」——
  本次會期補上了那個從未被做出的決定。
- 假設：分組行為以 `_pattern_check` 的確定性語意推導，未實跑真實 LLM 抽取（會花 token）。
  實作階段須以離線 `fake_extract` 覆蓋多 pattern／純殘餘／混合三種形態。

## Updated Artifacts

- 新增 `changes/phase-p5-run-2026-08-11/PHASE_REQUEST.md`（phase 停止與阻擋點證據）
- 新增 `changes/phase-p5-run-2026-08-11/DECISION_INVENTORY.md`
- 新增 `changes/phase-p5-run-2026-08-11/DECISION_READINESS_SUMMARY.md`（本檔）
- 未修改任何實作檔、未寫 ADR（本 repo 無 ADR 目錄）、未新增 glossary（`提案群組` 一詞沿用
  `docs/api_contract.md` 既有定義，語意未變）

## Recommended Next Workflow

Ready for plan-change

範圍：抽取路徑 per-group staging（G1–G3 已定案，I1–I5 為實作預設）。
不含 schema-gap backlog（DF1）與 gold 改打真實輸出（DF2）。

注意：本次交付**不會**使 roadmap 的 P5 完成——P5 的三個產出中，本次只交付第三個。
Roadmap 完成狀態不得因此變更。
