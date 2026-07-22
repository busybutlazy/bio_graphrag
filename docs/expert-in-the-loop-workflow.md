# Expert-in-the-loop 萃取治理 — 操作 workflow

> 上游計畫與決策紀錄見 `docs/expert-in-the-loop-plan.md`。本文件是**操作面**:一個案例
> 從 AI 提案走到固化成 gold 的每一步、每一關由誰負責、卡在哪就往哪去。

## 一句話

> 讓非工程背景的領域專家,也能參與 GraphRAG 萃取規則審查,
> 並把專家知識轉換成可測試、可追蹤、可演進的工程資產。

## 兩道 gate,形式與意義分離

| gate | 誰 | 只管 | 不管 | 實作 |
|---|---|---|---|---|
| 工程師 gate | 工程師/面試官 | 形式:schema、型別、id 慣例、三段式/Interaction 完整性、可反向翻譯、可測試 | 生物語意 | `backend/app/graph/engineer_gate.py` |
| 專家 gate | 領域專家 | 意義:是否符合原文、有無過度推論、有無漏概念、弱關聯誤判成因果、schema 表達不了的現象 | JSON / schema code | 前端 `renderExpertDemo` Tab3(強制隔離) |

最常見的失敗是「用 JSON valid 代替生物學正確」。因此工具用 **tab 邊界**強制隔離兩種審查面,
而不是靠自律:專家畫面**不顯示** raw JSON、schema code、node/edge id、內部 gap code、prompt。

## 一個案例的生命週期

1. **AI 提案** — 依原文與現有 schema 擬出 `proposal`(nodes/edges/references_existing/
   confidence/uncertain_points/possible_schema_gap)。
2. **工程師 gate(當場計算)** — `engineer_gate.evaluate` 逐項檢查形式,
   `result ∈ {pass, fail_schema, fail_pattern, fail_testability, needs_schema_extension}`。
   - `fail_*` → 退回修 proposal(形式問題,不勞煩專家)。
   - `needs_schema_extension` → 形式沒問題但現行 schema 表達不了(硬 gap),轉 backlog。
   - `pass` → 進反向翻譯。
3. **反向翻譯(deterministic)** — `back_translation.render_understanding` 以結構簽章
   pattern-match(P1–P5,無 LLM)產出白話「系統理解」。專家看到的就是 graph 真正表達的內容。
4. **專家 gate** — 專家只讀:原文、系統理解、概念圖、系統沒理解成什麼、審查選項、備註。
   - 同意 → 可固化成 gold。
   - 有疑慮 → 記備註,退回調整。
   - 無法表達 → 選白話 gap 選項,系統映射成 `schema_gap_type` 進 backlog(見
     `docs/schema-gap-policy.md`)。
5. **固化** — 通過的案例存成 gold 最小斷言(`data/sample/expert_demo/gold/*.json`),
   `backend/tests/gold/test_gold_examples.py` 逐條回歸。日後改 prompt/schema/pipeline 時,
   gold 就是防退步的網。

## Demo 怎麼看

- 前端「審閱」分頁(`renderExpertDemo`),資料源 `GET /admin/expert-demo/cases`(唯讀)。
- 左側 5 個定案案例;右側三 tab 對應上面的 gate:AI 提案 / 工程師 gate / 專家審閱。
- 五個案例:單一效果、多步驟 mechanism、分泌觸發、拮抗(fact-node 重用)、permissive 硬 gap。
  規格見 `docs/expert-in-the-loop-plan.md` 四。

## MVP 邊界

固定資料 demo;不接真 pipeline、不改 `schema/` 型別、不做 LLM 潤飾層。詳見計畫文件 §七。
