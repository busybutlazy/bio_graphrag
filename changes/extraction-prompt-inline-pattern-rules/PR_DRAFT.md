# PR 草稿

**標題**：`fix(extraction): make LLM proposals pass the Schema gate — and make the loop reviewable`

**base**：`main` ← **head**：`fix/extraction-prompt-inline-pattern-rules`（6 commits，16 檔，+802/-22）

---

## 本文（建議直接貼進 PR body）

抽取結果的 Schema gate 通過率是 0。根因不是模型能力，而是 prompt 要求模型遵守**兩份它讀不到的檔案**：規則 3 說「嚴格依照 `extraction_guidelines.md`」、規則 6 說「完全符合 `extraction_output_schema.json`」，但兩者都只給了檔名。模型只好用猜的——`HAS_EFFECT` 被讀成「有效果」，寫成 `RegulatoryEffect ─HAS_EFFECT→ PhysiologicalVariable`（正確應為 `ON_VARIABLE`），而且完全沒有提案 Hormone 節點與方向邊。

修法是把那些檔案真正說的話，寫在使用它的地方。

### 抽取規則（prompt）

- **rules 7–11 內聯**：三段式的固定方向、分泌觸發、Interaction、FeedbackLoop、id 慣例，各帶正例與實測觀察到的錯誤寫法。
- **rule 6 內聯輸出形狀**：最小 JSON 範例與必填欄位，因為「符合 schema 檔」犯的是同一個病。
- **三段式改成數量規則**：`ON_VARIABLE` 與方向邊端點相同、只有 type 不同，模型會把它們當成同一條邊寫兩次而壓成一條。改成「必須配恰好三條邊」，並明說 (2)(3) 共用端點但都要輸出。

### 治理缺口（審查發現）

- **P2 分泌觸發缺席**（H1）。`group_statements` 與 `back_translation` 都實作了 P2，但 prompt 從未描述它，而 rule 7 下的是無例外全稱令。碰到「血糖升高時 β 細胞分泌胰島素」，模型會硬造一個 RegulatoryEffect——它**通過** `_pattern_check`、**渲染成合理的 P1 句子**，因果卻是反的，只有專家看得出來。gate 亮綠燈、生物學錯誤，正是這條 pipeline 要防的事。
- **FeedbackLoop 沒有任何人看管**（M2）。它是合法節點型別，卻不在 `PATTERN_ANCHOR_TYPES`、gate 無分支、renderer 無 pattern、沒有 rule card。實測中 `feedback:blood_glucose_negative_feedback` 被摺進兩個調控效果群組裡：核准「胰島素降低血糖」的同時，一個從未被描述的迴路也一併寫進正式圖譜。現以 P6 端到端補齊（rule card → anchor → splitter 模板 → renderer → gate → prompt）。
- **gate 現在檢查 `interaction_type`**。缺這個屬性時 P4 renderer 進不去，專家對著課本級的拮抗讀到「不屬於任何已知的調控模式」，gate 卻回報 pass。與 FeedbackLoop 的 `feedback_type` 檢查同源，只修一半會變成兩套標準。
- **概念圖不再出現無名節點**。抽取被要求重用既有概念而非重新提案，所以邊經常指向不在佇列裡的**已核准**節點，前端把它們畫成「（相關概念）」灰球——專家看到「胰島素 ←分泌— （某物）」還被要求核准，而圖譜其實知道那是胰臟。現在會回查 `GET /nodes/{id}`；真的查無此節點則顯示 id 本身，因為斷邊是該被退回的缺陷，不該被 UI 美化。

### FeedbackLoop 的兩個刻意設計（rule card 有記錄）

1. **只要求一條 `USES_EFFECT`**，不是兩條。四個已核准迴路中有三個（血鈣、血漿滲透壓、子宮收縮）只引用單一效果；照抄 Interaction 會把專案自己策展過的知識判成不合格。
2. **被調控變因用節點屬性，不是 `ON_VARIABLE` 邊**。既有四個迴路本來就這樣建模，對齊它零成本；反過來要求邊則需改 `data/sample` 並重跑 `make export-seed`。Owner 決策。

### 測試

- `pytest tests ingestion/tests`（離線姿態）：**209 passed**。
- 新增守衛：base prompt 必須涵蓋每張 rule card 結構簽章裡的邊型別，比對前會**先剝除規則 2 的型別白名單**——白名單只是一串沒有方向資訊的名字，正是原始 bug 本身，會被它滿足的檢查等於沒檢查。實測套在修補前的 prompt 上會判定缺少 `SECRETES`、`REGULATES_SECRETION_OF`，即當初就會擋下 H1。
- 新增 splitter 回歸測試：兩效果的迴路必須整組claim，否則會被拆成兩組、residual 還會渲染出第二句迴路句子。這個 bug 是用真實抽取形狀驗證時抓到的，不是測試抓到的。

### 已知未解（不在本 PR）

抽取偶爾仍會有單一 edge 漏 `id` 而整個 chunk 被丟棄。三次付費抽取證實 prompt 層已到頂（system prompt、最小 JSON 範例、user prompt 末行 checklist、外加會回饋錯誤原文的重試，都無法歸零）。正解是 `llm_client.py` 改用 `json_schema` + `strict`，另案處理。

證據與未執行項目記在 `changes/extraction-prompt-inline-pattern-rules/VERIFICATION_REPORT.md`；審查報告與逐條處置在同目錄 `REVIEW_REPORT.md`。

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01CJ9gSma26bWd1QsFrGndEg
