# Review Report: extraction-prompt-inline-pattern-rules

## Review Context

- **Diff base and scope**：`main...fix/extraction-prompt-inline-pattern-rules`，單一 commit `2073546`。
  `git diff --stat` 確認為 `prompts/graph_extraction_prompt.md` 一檔，+50/-6。無 code、無依賴、無 migration。
- **Artifacts reviewed**：
  - diff 全文（`git show 2073546`）與 commit message 的完成宣稱
  - `ingestion/pipeline/build_extraction_prompt.py`（模板組裝）、`ingestion/extract/runner.py`（`_extract_chunk` 驗證/重試/丟棄路徑）
  - `schema/extraction_output_schema.json`、`schema/extraction_guidelines.md`、`schema/rule_cards/{single_regulatory_effect,secretion_trigger,antagonistic_interaction}.md`
  - `backend/app/graph/engineer_gate.py`、`backend/app/graph/back_translation.py`、`ingestion/pipeline/group_statements.py`、`backend/app/api/routes_review.py`
  - `ingestion/tests/test_build_extraction_prompt.py`；容器內實際執行 `pytest tests ingestion/tests`
  - `docs/notes.md`（untracked，工作區內的順序計畫表）
- **缺少的 artifacts**：本變更**沒有** `changes/<change-id>/` 目錄，沒有 IMPLEMENTATION_PLAN、VERIFICATION_REPORT、CHANGE_REPORT、TASK_LOG。倉庫中其餘 10 個 change 皆有。見 M3。
- **Independence disclosure**：本次審查在獨立 session 進行，未參與此 commit 的規劃或實作（commit 標記的 session 為 `session_01CJ9gSma26bWd1QsFrGndEg`，與本 session 不同）。但驗證所依據的「三次真實抽取」使用 gitignored 的私有章節，審查者無法取得該輸入，該部分只能做間接推論，不構成獨立複驗。

## Completion Claim Assessment

已用證據逐條檢驗宣稱，結論：**形式面宣稱全部成立；內容面的「已把那些檔案講的東西 inline 進來」只做到一部分**。

| 宣稱 | 判定 | 證據 |
|---|---|---|
| 只動一個檔案，無 code / 依賴 / contract 變更 | **成立** | `git diff --stat main...HEAD` 僅 1 檔；無 `pyproject.toml` 變動 |
| 模型讀不到 `extraction_guidelines.md` / `extraction_output_schema.json`，只拿到檔名 | **成立** | `build_extraction_prompt.py` 只讀 base 模板的前兩個 ` ```text ` 區塊 + optional profile；全庫無任何把 schema/guidelines 檔案內容注入 prompt 的路徑 |
| rule 6 inline 的 JSON 形狀符合 schema | **成立** | 逐欄比對 `extraction_output_schema.json`：node required `id/type/label/description/source_chunk_id`、optional `properties/possible_duplicate_of`；edge required `id/type/source/target/source_chunk_id`、optional `properties`；`additionalProperties:false` 對應「不要自行新增其他欄位」。全部一致 |
| rule 7/8 對應 Schema gate 的實際檢查 | **成立** | `engineer_gate._pattern_check`：RegulatoryEffect 需 HAS_EFFECT 入邊 + ON_VARIABLE 出邊 + INCREASES/DECREASES 出邊；Interaction 需 ≥2 USES_EFFECT + ON_VARIABLE。與 rule 7/8 字面一致 |
| rule 9 的 node id 慣例對應 gate | **成立** | `_ID_RE = ^[a-z_]+:[a-z0-9_]+$`；rule 7 範例 `hormone:insulin`、`regulatory_effect:...`、`physiological_variable:blood_glucose` 皆通過 |
| 「少一個欄位,整段抽取都會被丟棄」 | **大致成立**（見 L3 註） | `runner._extract_chunk` 對整個 chunk payload 做 `validate_extraction_output`，失敗則 `candidate=None`、`failed_chunks += 1`，整 chunk 不進 staging。惟中間有一次帶錯誤訊息的 retry，非「立即丟棄」 |
| 「輸出後處理」章節更新後與現況相符 | **成立** | `routes_review.py` 確有 `/review/groups/{group_id}/approve|reject|gap`；`group_statements.py` 確以 P1/P2/P4 + residual 切組 |
| 「Schema gate 由 fail_pattern 全面轉為 pass」 | **無法複驗** | 私有章節、無記錄命令、無前後計數、無 artifact。見 M3 |

**主動嘗試證偽而未成立的假設**（記錄下來，避免後續重覆懷疑）：rule 6 新增的字面大括號 `{"nodes": ...}` 是否會讓 `build_user_prompt` 的 `str.format()` 抛 `KeyError`。**不會** —— `.format()` 只作用在第二個 fenced block（user template），新大括號全在第一個 block（system prompt），而 `build_system_prompt` 走 f-string 代入變數、不格式化內容。容器內實測：`build_system_prompt(None)` 長度 2581、含 rule 9 與 `{"nodes"`；`build_user_prompt` 佔位符正常替換；`pytest ingestion/tests/test_build_extraction_prompt.py` 4 passed。

## Findings

### Blocking

無。

### High

**H1 — 三段式規則被 inline 了，但「分泌觸發」(P2) 的對應規則沒有，且 rule 7 的措辭會把 P2 推向錯誤結構**

- 位置：`prompts/graph_extraction_prompt.md:43`（rule 7「調控類一律走三段式,不可壓縮」）；缺漏對照 `schema/rule_cards/secretion_trigger.md`
- 事實：系統中確實存在第三個 pattern。`ingestion/pipeline/group_statements.py:_TEMPLATES` 有 P2 模板（`IN REGULATES_SECRETION_OF ×1` + `IN SECRETES ×1`），`back_translation.py:74-82` 有 P2 renderer 分支。但更新後的 prompt 只講了 P1（rule 7）與 P4（rule 8），**完全沒有提到 P2 的結構簽章，也沒有提到 `SECRETES` / `REGULATES_SECRETION_OF` 的方向**。
- 風險放大點：`secretion_trigger.md` 明文寫「**本 pattern 沒有 RegulatoryEffect** —— 血糖升高是觸發條件,不是胰島素造成的效果,這是正確性關鍵」，並把「把觸發誤成效果」列為第一號常見誤解。rule 7 現在對模型下的是無例外的全稱命令（「調控類**一律**走三段式,不可壓縮」），沒有為分泌觸發留出口。
- 影響：面對「當血糖升高時,β 細胞分泌胰島素」這類句子，模型有明確誘因去硬造一個 RegulatoryEffect 三段式。這種輸出**通過** `_pattern_check`（三條邊齊全）、**通過** back_translation（會渲染成 P1「…會造成一個調控效果」），gate 全綠，**只有專家能發現因果被講反**。也就是說本變更提升的 `pass` 率，有一部分可能是把 P2 語句包裝成形式合格的 P1，而不是抽取變正確。這與 commit 的成功指標（gate 回報 pass）直接相關，是本次「pass 率上升」最需要排除的替代解釋。
- 修補方向（有界）：在 system prompt 增列一條 P2 規則，寫出 `Structure ─SECRETES→ Hormone` 與 `PhysiologicalVariable ─REGULATES_SECRETION_OF→ Hormone (properties.trigger_direction: increase|decrease)`，並在 rule 7 加一句除外條款：「分泌觸發不建 RegulatoryEffect」。不需改 code。

**H2 — rule 8 漏掉 `properties.interaction_type`，Interaction 會通過 gate 卻在專家畫面降級成「不屬於任何已知的調控模式」**

- 位置：`prompts/graph_extraction_prompt.md:60-63`（rule 8）vs `backend/app/graph/back_translation.py:88-90`
- 事實：P4 renderer 的進入條件是 `t == "Interaction" and props[nid].get("interaction_type") == "antagonism"`。`schema/extraction_guidelines.md`「什麼時候建立 Interaction」與 `rule_cards/antagonistic_interaction.md` 結構簽章都明寫 `Interaction { interaction_type: antagonism }`（另有 `synergism`）。本次 inline 把 USES_EFFECT ×2 + ON_VARIABLE 帶進來了，**但把 `interaction_type` 留在了模型讀不到的檔案裡**；rule 6 的形狀範例也沒有示範 `properties` 該放什麼。
- 影響：模型照 rule 8 生出的 Interaction 沒有 `interaction_type` → `_pattern_check` 通過（它不看 properties）→ `testability` 也通過（P0 的 `is_gap` 為 False）→ gate 回報 `pass`，但專家看到的句子是 `back_translation.py` 尾端的保底文字「本提案描述了…等概念及其關係,但不屬於任何已知的調控模式;請就內容本身審查」，而不是「A 與 B …在血糖上呈現拮抗」。gate 綠燈、lens 失真，正好打在本專案的治理主軸上。此外 `rule_cards` 的最小斷言（gold）以 `has_node_types: Interaction` 為準，lens 降級不會被自動測試接住。
- 修補方向（有界）：rule 8 增列「Interaction 必須帶 `properties: {"interaction_type": "antagonism"|"synergism"}`」，並在 rule 6 的 JSON 範例中示範一個帶 `properties` 的節點，以免 rule 6 的「不要自行新增其他欄位」被讀成「不要用 properties」。

### Medium

**M1 — rule 3 的交叉引用沒有兌現：規則 7 講的是「怎麼接」，不是「何時建」**

- 位置：`prompts/graph_extraction_prompt.md:21`「何時建立 RegulatoryEffect / Interaction 見下方規則 7、8」
- 事實：rule 8 確實含一條 when 條件（沒有兩個 RegulatoryEffect 之前不要建 Interaction）；rule 7 則純粹是方向與結構，**沒有任何一句說明何時該建立 RegulatoryEffect**。`extraction_guidelines.md` 原本的判準（「只在文本明確描述『誰對什麼生理變因造成什麼方向的效果』時建立」）沒有被 inline。
- 影響：commit 宣稱的方法是「Inline what those files actually say」，在 RegulatoryEffect 的 when 判準上未達成——以 how 規則替換了 when 規則，指標卻仍寫著「何時建立…見規則 7」。與 H1 疊加後，模型缺少任何「這句話不該建 RegulatoryEffect」的抑制條件。
- 修補方向：在 rule 7 開頭補回一句成立條件，或把 rule 3 的措辭改成不承諾 when。

**M2 — FeedbackLoop 只保留判準、丟掉結構，且無任何下游檢查會攔它**

- 位置：`prompts/graph_extraction_prompt.md:22-23`
- 事實：`extraction_guidelines.md` 對 FeedbackLoop 規定了 `USES_EFFECT` 連接迴路中的 RegulatoryEffect，以及 `feedback_type: negative|positive`。inline 後只剩「閉環才建」一句，結構與屬性全失。而 `PATTERN_ANCHOR_TYPES = {"RegulatoryEffect", "Interaction"}`（`normalize_concepts.py:49`）不含 FeedbackLoop，`_pattern_check` 沒有 FeedbackLoop 分支，back_translation 也沒有對應 pattern。
- 影響：模型若生出 FeedbackLoop，邊是自由發揮的；它不會形成 anchor group、掉進 residual、渲染成 P0 白話摘要，形式面**完全無人檢查**就送到專家眼前。頻率取決於教材，但一旦發生沒有任何自動防線。
- 修補方向：二選一——inline FeedbackLoop 的結構簽章與 `feedback_type`；或明確指示在 rule card 補齊前不要產生 FeedbackLoop（後者更符合 YAGNI 與「寧缺勿濫」）。

**M3 — 驗證證據不可複驗，且缺少流程要求的 change artifacts**

- 事實：本變更無 `changes/<change-id>/` 目錄（對照 `changes/` 下既有 10 個變更皆備 plan/verification/change report）。唯一的驗證陳述是 commit message 中的一段話：「Verified against three real extractions of a private chapter (gpt-4o-mini, markdown_header)」。無執行命令、無 job id、無前後群組數/gate 結果計數、無保留任何輸出；輸入章節為 gitignored 私有資料。
- 違反：`CLAUDE.md` 開發流程第 2、5、6 步（implementation plan → 如實記錄命令與結果 → 變更報告）。
- 影響：核心成效宣稱（「fail_pattern 全面轉 pass」）目前只能相信作者敘述。且因 H1 存在一個替代解釋（P2 語句被包成形式合格的 P1 也會讓 pass 率上升），沒有留存輸出就無法區分「抽得更對」與「錯得更整齊」。
- 修補方向：補一份 VERIFICATION_REPORT，至少記錄執行命令、chunk 數、每組 gate result 的前後計數，以及 P2/P4 語句的實際渲染句（可去識別化，不需附章節原文）。

**M4 — 與 `docs/notes.md` 的排序計畫不一致（範圍問題）**

- 事實：工作區 untracked 的 `docs/notes.md` 把「為 endocrine_demo_v1 寫 extraction profile：限定型別、講清楚 HAS_EFFECT／ON_VARIABLE 方向、附正確範例」列為 **N2，範圍註明「新 change（含一次花 token 的驗證）」**，且排在 N1（Structured Outputs）之後。本 commit 實質交付了 N2 的方向說明與正確範例，但放在**公開 base 模板**而非 profile，也沒有經過 N1，且無 plan/approval 紀錄。
- 影響：兩點需要人類裁決。(a) 本次是否有意把 N2 提前並改變其落點（profile → base 模板）；(b) N2 原本規劃的「一次花 token 的驗證」是否就是 commit message 裡那三次抽取——若是，該次驗證的證據標準未達 N2 的原意。
- 註記：`notes.md` 未進版控，可能已被更新的口頭決策取代；此處只陳述不一致，不推定違規。
- IP 邊界另行確認：inline 的內容（型別白名單、三段式、insulin/blood glucose 範例）在 `schema/`、`data/sample/`、`rule_cards/` 均已公開，放進公開 base 模板**沒有**外洩私有章節 IP。此項檢查通過。

### Low

**L1 — system prompt 體積增為 3 倍，每個 chunk 都會送一次，commit 未揭露成本影響**
838 → 2581 字元（實測 `build_system_prompt(None)`）。system prompt 每 chunk 一次隨請求送出，一章 30 chunk 的付費抽取約多出數萬 input tokens。金額不大但屬於「花 token 的動作」，依專案慣例應在報告中揭露。

**L2 — Misconception 建立時機與去重判準未 inline**
`extraction_guidelines.md` 的這兩節同樣沒被帶進來。rule 6 保留了 `possible_duplicate_of` 欄位，卻沒有任何一句說明何時該填；`Misconception` 仍在 rule 1 的白名單內但無判準。與 H1/H2 同源，影響較小。

**L3 — rule 6 的邊 id 範例 `e:<chunk_id>:1` 使用角括號佔位符，schema 不會攔**
edge `id` 在 schema 中無 pattern 限制（僅 `type: string`），`_ID_RE` 也只檢查 node id。若模型照字面輸出 `e:<chunk_id>:1`，驗證與 gate 皆會放行，產生字面含角括號的邊 id。另註：rule 6 的「整段抽取都會被丟棄」在 `_extract_chunk` 中實際上是「retry 用完之後才丟棄」（`runner.py:126-149` 會把驗證錯誤附回 user prompt 重試一次）。作為對模型施壓的措辭可接受，但與程式行為不完全等價。

**L4 — 工作區狀態：`docs/notes.md` untracked**
非本 commit 產物，但屬於未說明的工作區狀態，依規範記錄不繞過。內容為規劃筆記，未進版控。

### Suggestion

**S1 — 抽取規則現在有兩份真理，建議加一條行為守衛**
rules 7-9 是 `engineer_gate._pattern_check`、`group_statements._TEMPLATES` 與 `schema/rule_cards/` 的第四份副本，且是唯一一份純文字、沒有測試保護的副本。本倉庫已有現成做法：`group_statements.py` docstring 記載「Two behavioural guards in the backend tests keep the two copies honest」。建議比照，加一個測試斷言 base 模板的 system prompt 提及每個 `PATTERN_ANCHOR_TYPES` 與每張 rule card 的必要邊型別——這會在當初就抓到 H1（P2 缺席）。

## Requirement and Test Coverage Gaps

- 本變更**沒有新增任何測試**。既有 `ingestion/tests/test_build_extraction_prompt.py` 只驗證組裝機制（overlay、佔位符替換），不驗證模板內容，因此 rules 7-9 的正確性與完整性完全沒有自動化覆蓋——H1、H2、M2 三項都是「測試不可能發現」的類別。
- 本次改動的成效指標（gate result 分布）本質上依賴付費 LLM 輸出，難以在 CI 內斷言。**但可測的部分沒被測**：模板是否覆蓋所有 rule card 的必要邊型別、是否覆蓋所有 `PATTERN_ANCHOR_TYPES`，都是純字串檢查（見 S1）。
- 容器內完整測試實測結果：`docker compose run --rm backend pytest tests ingestion/tests -q` → **199 passed, 1 failed, 268.80s**。唯一失敗為 `ingestion/tests/test_pipeline.py::test_qdrant_payload_is_queryable`。歸因：查詢 Qdrant 得 `biology_chunks` 的 `points_count: 0`，本機 volume 未 seed；該測試不讀取 prompt 模板，doc-only 的 diff 在因果上無法影響它。屬環境狀態失敗，非本變更回歸——但也因此本次「無回歸」的結論是建立在 199 項通過 + 因果推論之上，而非一次全綠的 `make test`。

## Compatibility, Security, and Scope Assessment

- **相容性**：無 API、schema、DB、依賴變更。模板的兩個 ` ```text ` fenced block 結構維持不變（未新增 fence），`_FENCE_RE` 解析行為經實測確認未受影響。舊有 profile overlay 機制不受影響。
- **安全性**：無新增輸入路徑。node type 白名單驗證仍在 create time（`normalize_concepts`），本變更未觸及 Cypher label 插值路徑。prompt 內容不含任何憑證或私有章節文字。
- **`status='approved'` 不變式**：未受影響，本變更不產生任何進入 retrieval 的資料，所有產出仍需經 group review。
- **範圍**：diff 本身完全落在宣稱範圍內，無夾帶修改。範圍上的疑慮不在 diff，而在與 `notes.md` 排序計畫的關係（M4）。
- **Rollback**：單檔 doc 變更，`git revert 2073546` 即可，無狀態殘留。commit message 未寫 rollback，但風險可忽略。

## Unreviewed Areas and Residual Risk

- **未複驗**：commit 宣稱的三次真實抽取。輸入為 gitignored 私有章節，審查者無法取得，也未執行任何付費抽取。本報告對「pass 率是否真的上升」不表意見，只指出 H1 提供了一個未被排除的替代解釋。
- **未評估**：prompt 措辭對不同模型（非 gpt-4o-mini）的遷移效果；不同 chunk strategy（非 markdown_header）下的表現。
- **未執行**：`make eval`（22 題黃金題）。本變更不影響 retrieval 路徑，判斷無關聯，但未實測。
- **殘餘風險最高處**：gate 綠燈但語意錯誤的輸出（H1）與 gate 綠燈但 lens 降級的輸出（H2）。兩者都不會被任何自動檢查攔下，全部落在專家人工審閱上——而專家審閱正是這條 pipeline 中最貴的資源。

## Human Disposition Required

以下需要人類裁決，審查者不代決：

1. H1／H2 是否在本變更內補上（都只需改同一個檔案，不擴大範圍），或另開 change 處理。
2. M3：是否補 VERIFICATION_REPORT 與 change artifacts 後才合併。
3. M4：本次是否有意提前並改變 N2 的落點（base 模板 vs profile），以及 N2 是否視為已部分交付。

The reviewer does not approve, fix, merge, or release this change.

---

## 附錄：作者核實與處置（由實作者補記，上方審查內容未經修改）

上方 findings 全部逐條複驗。**技術判斷全部成立**，僅一處歸因需更正（見 A2）。

### A1 已修補（皆在 `prompts/graph_extraction_prompt.md` 內，未擴大範圍）

| Finding | 複驗結果 | 處置 |
|---|---|---|
| H1 P2 缺席 | **成立**。`group_statements._TEMPLATES` 有 P2 模板、`back_translation.py:74-82` 有 P2 renderer，但 prompt 只講 P1/P4，且 rule 7 的「一律走三段式」是無例外全稱命令 | 新增規則 8（`Structure ─SECRETES→ Hormone` + `PhysiologicalVariable ─REGULATES_SECRETION_OF→ Hormone` 含 `trigger_direction`），並在規則 7 加除外條款「分泌觸發不建 RegulatoryEffect」 |
| H2 缺 `interaction_type` | **成立**。`back_translation.py:88-90` 進入 P4 的條件是 `interaction_type == "antagonism"`；缺屬性會落到尾端 P0 保底句且 `is_gap: False`，gate 仍回報 `pass` | 規則 9（原 8）增列 `interaction_type: antagonism\|synergism` 為必填，並在規則 6 的 JSON 範例示範一個帶 `properties` 的節點 |
| M1 rule 3 交叉引用未兌現 | **成立**。原規則 7 只講 how 不講 when | 規則 7 開頭補回成立條件（「只在文本明確描述某調控者對某生理變因造成什麼方向的效果時建立」） |
| L3 角括號佔位符 | **成立**。edge id 在 schema 無 pattern、`_ID_RE` 只驗 node id，字面角括號會一路放行 | edge id 範例改為 `e1`/`e2`，並加一句「佔位說明必須換成真值,不可原樣照抄」 |
| S1 缺行為守衛 | **成立且採納** | 新增 `test_base_prompt_covers_every_rule_card_signature` 與 `test_base_prompt_mentions_every_pattern_anchor_type`。守衛會先剝除規則 2 的型別白名單再比對——否則會被「一串沒有方向資訊的名字」滿足，正是原始 bug。實測套在修補前的 prompt 上判定缺少 `['SECRETES', 'REGULATES_SECRETION_OF']`，確認當初就會擋下 H1 |
| M3 缺 artifacts | **成立** | 補 `VERIFICATION_REPORT.md`，記錄三次抽取的命令、逐次 failed_chunks、失敗 edge 明細、gate 前後分布，以及未執行項目 |

測試：修補後 `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`
→ **202 passed**（修補前 200，新增 2 項守衛）。

M3 另有一項可直接回答：報告指出「pass 率上升可能是 P2 被包成形式合格的 P1」這個替代解釋，
**在本次數據中不成立**——通過 gate 的兩組都是 `proposed_edges: []` 的 residual 概念群組，
不含任何 pattern。詳見 VERIFICATION_REPORT 2.2。

### A2 歸因更正（結論不變）

報告 §Requirement and Test Coverage Gaps 將 `test_qdrant_payload_is_queryable`
的失敗歸因為「本機 volume 未 seed」。**seed 確實跑過**：實測當時
`biology_chunks` 0 點、`biology_chunks_1536` 9 點——`.env` 有真實
`OPENAI_API_KEY` 時 seed 會寫進 1536 維 collection，而該測試寫死讀 `biology_chunks`
（既有 backlog：測試應查目前使用中的 collection）。之後以離線姿態跑過測試，
hash embeddings 灌進 `biology_chunks`，兩種姿態便都通過（實測 1 passed）。
報告「非本變更回歸」的結論不受影響。

### A3 待人類裁決（未自行處置）

- **M2 FeedbackLoop**：複驗成立（`PATTERN_ANCHOR_TYPES` 不含 FeedbackLoop、
  `_pattern_check` 無分支、renderer 無 pattern，形式面確實無人檢查）。但兩個選項
  ——inline 結構簽章 vs. 在 rule card 補齊前禁止產生——是生物語意範圍決策，
  影響「哪些知識會被提案」，屬 owner（領域專家）職權，實作者不代決。
- **M4 與 `docs/notes.md` 排序不一致**：陳述屬實，需 owner 確認是否有意提前 N2
  並改變落點（profile → base 模板）。
- **合併前建議**：本輪修補尚無真實抽取證據（見 VERIFICATION_REPORT §4），
  建議補跑一次，重點確認 P2 語句不再被包成 RegulatoryEffect。
