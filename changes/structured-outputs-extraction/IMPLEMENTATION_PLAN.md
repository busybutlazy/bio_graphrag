# Implementation Plan: structured-outputs-extraction

對應 `docs/notes.md` 的 **N1**:Structured Outputs(`json_schema` + `strict`)+ 逐元素失敗而非整塊丟棄。

## Objective

讓一條格式不合格的元素不再讓整個 chunk 的抽取結果消失。兩層防線:第一層用 OpenAI Structured
Outputs 從源頭約束模型輸出形狀;第二層在驗證仍失敗時**逐元素挑掉壞的、保留好的**,並如實揭露
被丟棄的內容——不揭露的部分保留就是靜默資料遺失,與本專案的稽核治理主軸直接衝突。

## In Scope

- `ingestion/extract/llm_client.py`:改用 `response_format={"type": "json_schema", ...}`(strict)。
- 一份 **API 面向的 strict schema** 的來源(位置見 D2)。
- `ingestion/extract/runner.py::_extract_chunk` 與 `ingest_document`:逐元素挽救 + 揭露欄位。
- `ingestion/pipeline/validate_extraction.py`:新增單一 node/edge 的驗證輔助函式。
- `docs/api_contract.md`:記錄 `POST /admin/ingest/run` 回應新增的欄位。
- 對應測試(離線,以注入的 `extract_fn` 驅動)。

## Out of Scope

- 不改 `schema/extraction_output_schema.json` 對**內部驗證**的語意(它同時是 `engineer_gate.evaluate`
  對人工提案的驗證來源,見 D2 的風險說明)。
- 不改 prompt 措辭、不做 N2 的章節 profile。
- 不重新設計 retry 策略(`retries=1` 維持)。
- 不改群組切分、staging、gate、lens 的任何語意。
- 不改 embedding / Qdrant / 前端。

## Current-State Evidence

- **Repository state**:分支 `main`,工作區乾淨,僅兩個未追蹤檔:`docs/notes.md`(既有規劃筆記)
  與 `changes/extraction-prompt-inline-pattern-rules/PR_DRAFT.md`(上一個變更的 PR 草稿)。兩者皆不屬本變更。
- **Relevant files and symbols**:
  - `ingestion/extract/llm_client.py:41-51` —— `client.chat.completions.create(...)`,目前
    `response_format={"type": "json_object"}`,**未設 `max_tokens`**。`openai` 版本 1.109.1
    (`backend/requirements.txt:8` 為 `openai>=1.40,<2`),模型 `gpt-4o-mini`。
  - `ingestion/extract/runner.py:111-149` —— `_extract_chunk(extract_fn, ..., retries)`:
    第 135 行 `validate_extraction.validate_extraction_output(candidate)` 對**整包**驗證,
    任一元素不合格即進 `except`,重試時把錯誤原文附回 user prompt;重試用盡回 `(None, tokens, last_error)`。
  - `ingestion/extract/runner.py:254-257` —— `candidate is None` → `extraction_failed = True`、
    `failed_chunks += 1`,該 chunk **完全不進 staging**。
  - `ingestion/extract/runner.py:42-52` —— `ChunkReport`,即 API 回應中 `chunks[]` 的形狀。
  - `ingestion/pipeline/validate_extraction.py` —— 單一函式 `validate_extraction_output`,
    載入 `schema/extraction_output_schema.json`。
  - **同一個 schema 也被 `backend/app/graph/engineer_gate.py:96` 使用**,對**所有**提案
    (含人工建立的)做 `schema_validation` 檢查——這是 D2 的關鍵限制。
  - `extract_fn` 為可注入參數(`runner.py:159,175`),既有測試以假造函式驅動
    (`ingestion/tests/test_document_ingest.py:58,140,380`),因此挽救邏輯**可完全離線測試**。
- **Existing behavior and baseline tests**:
  - 基準:`docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`
    → **209 passed**(2026-08-12,`main` @ `c292a68`)。無既有失敗。
  - 觀察到的失敗形態(前一變更的 `VERIFICATION_REPORT.md` 有完整記錄):三次付費抽取,
    每次都有 chunk 因**單一一條** edge 缺 `id`(或欄位寫成 `relationship`)而整段被丟棄;
    重試已把錯誤原文回饋給模型仍失敗。
  - **嚴重度已下降**:prompt 修補後 owner 最近一次抽取為 3 chunks、`failed_chunks: 0`。
    問題從「每次都掉」變成偶發。這是**觀察**,不是保證——樣本數小。

## Acceptance Criteria

1. 一個 chunk 的模型輸出含一條不合格 edge 時,其餘合格的 node/edge **仍進入 staging**;
   該 chunk 不再計入 `failed_chunks`(離線測試,注入 `extract_fn`)。
2. 每個被丟棄的元素都在該 chunk 的報告中被列出(id 或原始片段 + 原因),並計入 job `stats`;
   一次沒有丟棄的執行,對應計數為 0。
3. 挽救**不得**留下懸空邊:端點被丟棄的邊必須一併丟棄,並同樣揭露。
4. 全部元素都不合格時,行為與現況一致(該 chunk 記為失敗),不得回報成功。
4b. 被丟棄比例超過門檻的 chunk 仍照常挽救並進入佇列,但在報告中被標記為 `degraded`(D1b)。
5. `POST /admin/ingest/run` 的新欄位與 `docs/api_contract.md` 描述一致。
6. 離線姿態不變:未設 `OPENAI_API_KEY` 時完全不觸及 API 路徑,既有離線測試全數維持通過。
7. 完整離線測試 ≥ 209 passed 且無新失敗;`ruff check` / `ruff format --check` / `mypy` 皆過。
8. (需 D3 批准)一次真實抽取:API 接受 strict schema,且該章節不再出現整塊丟棄。

## Contract, Schema, Dependency, and Migration Impact

- **Contract(additive)**:`POST /admin/ingest/run` 回應的 `stats` 與 `chunks[]` 新增揭露欄位。
  既有欄位不改名、不改語意。`docs/api_contract.md` 第 246-254 節需同步。
- **Schema**:視 D2 決定。**若選 (c) 直接改 `extraction_output_schema.json` 為 strict 相容,
  會連帶改變 `engineer_gate` 對人工提案的驗證**——目前 `properties`、`possible_duplicate_of`
  為選用,strict 要求所有屬性列入 `required`,人工提案若未帶這些鍵將開始被判 `fail_schema`。
  這是既有功能的迴歸風險,不是純新增。
- **Dependency**:無新增。`openai` 1.109.1 已支援 `json_schema` response format;`gpt-4o-mini` 支援 strict。
- **Migration**:無。不動資料庫結構,不刪改既有列。

## Execution Policy

- **Plan revision**:3(revision 2 之後,owner 依審查 H1 要求把前端揭露納入本變更;
  範圍擴大內容見〈Task 6〉與下方路徑範圍)
- **Risk level**:**高**。理由:(a) 變更公開記載的 API 回應契約;(b) 改變「什麼知識會進入審閱佇列」
  ——從全有全無改為部分接受,揭露若不完整就是靜默資料遺失;(c) D2 選項 (c) 會迴歸影響人工提案驗證。
- **Automation mode**:`one-task-at-a-time`(依 `docs/agent-guideline.md` 風險分級,高風險不得使用 `supervised-auto`)
- **Auto-approved task IDs**:無(不適用)
- **Approved file/path scope**:`ingestion/extract/`、`ingestion/pipeline/validate_extraction.py`、
  `ingestion/tests/`、`schema/`(僅 D2 決定的檔案)、`docs/api_contract.md`、`changes/structured-outputs-extraction/`
  —— revision 3 追加(owner 明示批准):`frontend/app.js`、`frontend/index.html`(僅資產版本號)。
  **`backend/tests/unit/` 仍在批准範圍外**:revision 2 期間已發生的路徑偏離
  尚未被追認,列於 `CHANGE_REPORT.md`〈Plan Deviations〉待人類裁定,不得視為已批准。
- **Human checkpoints**:每個 Task 完成後回報並等待批准;T1 與 T5 的 token 花費各需獨立批准。
- **Mandatory stop conditions**:需要改動 `engineer_gate` 或人工提案路徑;需要新增 dependency;
  發現必須修改既有 `extraction_output_schema.json` 的內部語意;真實抽取顯示挽救行為與計畫不符;
  任何既有測試轉紅。
- **Commit/push permission**:**No unless separately approved after review.**

### 已裁決事項(2026-08-12,owner)

- **D1(a) 連帶丟棄**:節點被丟棄時,指向它的邊**一併丟棄**並同樣揭露。否則會產生
  `approve_group` 既有防線本來就會擋下的懸空邊。
- **D1(b) 下限**:設門檻但**只揭露不擋**。任何比例都照常挽救並進入佇列;被丟棄比例超過門檻時,
  該 chunk 在報告中額外標記為 `degraded`。擋下來等於回到「整塊丟掉」的老問題;不標記則模型
  系統性退步時 job 仍回報 success 而無人察覺。
- **D2 strict schema 位置**:**執行期推導**。`schema/extraction_output_schema.json` 維持唯一真相
  且不改動,內部驗證與 `engineer_gate` 對人工提案的行為**逐字不變**;另加純函式
  `build_strict_schema()` 在送出請求前轉換(所有屬性入 `required`、選用欄位改為可為 null、
  剝除 strict 不支援的關鍵字)。
- **D4**:維持**高風險** / `one-task-at-a-time`。

## Tasks

### Task 1 — 確認 API 接受我們的 strict schema(spike,需批准 token 花費)

- Files/symbols:唯讀 + 一支拋棄式探測腳本(不進版控)
- Implementation:以既有 `extraction_output_schema.json` 推導 strict 版本,對 `gpt-4o-mini`
  發**一次**最小請求,確認:(a) 請求被接受;(b) `pattern`(node id 的 `^[a-z_]+:[a-z0-9_]+$`)
  等關鍵字是否被 strict 模式接受;(c) 回應是否可能帶 `refusal`。
- Tests and container command:`docker compose run --rm backend python /app/scripts/<probe>.py`
  (腳本置於 scratchpad,不留在 repo)
- Stop/handoff:記錄哪些關鍵字必須從 API 面向 schema 剝除;若 API 拒絕整份 schema,停止並回報,
  因為那會使 D2 的選項改變。**估計成本 < 1 分美元。**

### Task 2 — strict schema 來源 + `llm_client` 改用 json_schema

- Files/symbols:`ingestion/extract/llm_client.py::extract`,加一個純函式(例如 `build_strict_schema()`)
  置於 D2 決定的位置
- Implementation:把 schema 組裝抽成**純函式**以便離線斷言(目前 `extract` 內部直接 `OpenAI()`,
  沒有測試接縫);`extract` 改送 `response_format={"type":"json_schema","json_schema":{...,"strict":True}}`;
  處理 `refusal`(視 T1 結果)。
- Tests and container command:新增 `ingestion/tests/test_llm_client_schema.py` 斷言純函式輸出
  (所有屬性入 `required`、`additionalProperties:false`、T1 判定不支援的關鍵字已剝除、與內部
  schema 的必填欄位一致)。`docker compose build backend && docker compose run --rm -e OPENAI_API_KEY= backend pytest ingestion/tests -q`
- Stop/handoff:不在本 Task 動 runner。

### Task 3 — 逐元素挽救 + 揭露

- Files/symbols:`ingestion/extract/runner.py::_extract_chunk`、`ingest_document`、`ChunkReport`;
  `ingestion/pipeline/validate_extraction.py` 新增 `validate_node` / `validate_edge`
- Implementation:整包驗證失敗時,逐元素驗證、挑掉不合格者;依 D1 決定處理節點被丟棄後的
  懸空邊;把丟棄清單寫入 `ChunkReport` 與 job `stats`;全數不合格時維持現有的 chunk 失敗行為。
- Tests and container command:離線,以注入 `extract_fn` 覆蓋:一條壞 edge、一個壞 node
  (含其依賴邊)、全部壞、完全乾淨(不得有行為變化)、重跑冪等(修好後再跑會補進先前被丟棄的元素)。
  `docker compose build backend && docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`
- Stop/handoff:若挽救後的元素會讓群組切分產生懸空邊,停止回報(與 `approve_group` 的既有防線衝突)。

### Task 4 — 契約文件同步

- Files/symbols:`docs/api_contract.md`(`POST /admin/ingest/run` 一節)
- Implementation:記錄新欄位的名稱、型別、語意,以及「部分接受」這個行為改變。
- Tests and container command:無自動測試;以 Task 3 的實際回應對照人工檢查。
- Stop/handoff:文件與實作不一致即停止。

### Task 5 — 完整驗證(需批准 token 花費)

- Files/symbols:`changes/structured-outputs-extraction/VERIFICATION_REPORT.md`
- Implementation:完整離線測試 + lint/mypy + 一次真實抽取前後對照。
- Tests and container command:
  - `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`
  - `docker run --rm -v $PWD:/w -w /w python:3.12-slim sh -c "pip install -q -r backend/requirements-dev.txt && ruff check <paths> && ruff format --check <paths> && mypy backend/app ingestion scripts"`
  - 真實抽取:`POST /admin/ingest/run`(owner token),記錄 `failed_chunks`、丟棄清單、群組數
- Stop/handoff:寫出報告後停止,交由獨立審查。

## Verification Strategy

- **Normal**:乾淨輸出的抽取行為與現況逐欄位相同(避免挽救路徑污染正常路徑)。
- **Boundary**:恰好一條壞 edge;恰好一個壞 node;壞元素位於輸出最後(實測失敗都出現在靠後位置)。
- **Failure**:全部元素不合格;LLM 回傳非 JSON;API 回 `refusal`;重試後才成功。
- **Compatibility**:未設 `OPENAI_API_KEY` 的離線路徑不受影響;`engineer_gate` 對人工提案的
  `schema_validation` 行為**逐字不變**(以既有測試為證)。
- **Security**:不新增輸入路徑;不改 `/admin` 認證;丟棄清單寫入報告時不得回填原始 chunk 文字
  以外的私有內容(章節本文本來就在回應中)。
- 所有命令一律走既有容器入口;測試檔改動後必須先 `docker compose build backend`(測試未掛 volume)。

## Risks and Unknowns

- **U1**(未知):strict 模式是否接受 `pattern` 等字串約束。影響 API 面向 schema 的內容。
  由 Task 1 判定,不以假設推進。
- **U2**(風險):若把單一 schema 直接改為 strict 相容,`engineer_gate` 對人工提案的驗證會跟著變嚴,
  現有未帶 `properties` 的人工提案將開始被判 `fail_schema`。這是 D2 的核心取捨。
- **U3**(風險):挽救可能掩蓋系統性劣化——例如模型大幅退步、九成元素被丟棄,job 仍回報 success。
  對策見 D1 的第二問(是否設下限)。
- **U4**(風險):部分接受與冪等的交互作用。`group_id` 由 chunk + focus 推導、staging 用
  `ON CONFLICT DO NOTHING`,修好後重跑應該會補上先前丟棄的元素;需以測試證明,不假設。
- **U5**(觀察):嚴重度已下降(最近一次真實抽取 `failed_chunks: 0`),故本變更的即時收益可能
  低於前一次評估。若 owner 認為應優先做 N3(lens 敘述品質),這份計畫可原樣擱置。

## Rollback

單純 revert 本變更的 commits 即可,無資料 migration、無 schema 破壞性改動。
若在部分接受上線後才 rollback:期間 staged 的提案仍是 `proposed` 狀態的正常列,
可照常審閱或退回,不需要資料修補。

## Human Decisions and Approval

- **Decisions required**:
  - ~~D1(a) 連帶丟棄~~ / ~~D1(b) 下限~~ / ~~D2 strict schema 位置~~ / ~~D4 風險與模式~~
    —— 均已裁決,見〈已裁決事項〉。
  - **D3 token 花費**:**仍未批准**。Task 1 的探測(< 1 分美元)與 Task 5 的真實抽取
    (約 0.2 分美元)各需在執行前取得批准;兩者本來就是 human checkpoint。
- **Status**:Approved(revision 2)
- **Approved plan revision**:2
- **Approved risk level and automation mode**:高 / `one-task-at-a-time`
- **Approved by/date**:owner,2026-08-12。批准依據:於本 session 明示「N1 還是可以先做」,
  並逐項裁決 D1(a)、D1(b)、D2、D4。D3 不在此批准範圍內。
- **Approval evidence**:**Not approved until a human explicitly records it here. Material plan changes invalidate approval.**

---

## Task 6 —— 前端揭露(revision 3 追加,對應審查 H1)

**為什麼加進本變更而非另立 change**:owner 判定「只完成後端端點不算完成」。
本變更把失敗模式從「大聲」(整塊失敗,UI 有紅色警告)改成「安靜」(逐元素丟棄,UI 完全無感),
而唯一的人類介面沒有跟上——揭露只到機器看得到的地方,等於沒有揭露。
`runner.py` 的註解自述「揭露就是全部的重點」,若不補,這句話在成品上不成立。

- **Files/symbols**:`frontend/app.js::renderRunResult`;`frontend/index.html`(資產版本號)
- **Implementation**:
  1. 統計磚新增「丟棄(節點/關係)」,非零時標紅;`degraded_chunks` 非零時另加一磚。
  2. 有任何丟棄時,於成功通知下方加一句說明「部分接受」的實際後果。
  3. 逐塊卡片:有丟棄時列出每一筆(kind、id、reason),沿用既有 `.chunk-fail` 樣式;
     `degraded` 的塊在標頭標示,**使被挽救的塊與乾淨的塊在視覺上不可能混淆**。
- **Tests and container command**:前端為零建置 vanilla SPA,倉庫**沒有前端測試設施**,
  故無自動化測試可加(如實記錄,不假裝有覆蓋)。驗證方式:
  `docker run --rm -v $PWD/frontend:/w:ro node:20-alpine node --check /w/app.js`
  + 與 `runner.py` 的 stats/ChunkReport 欄位名逐一對照。
- **Stop/handoff**:不改後端、不改欄位語意;若發現需要新欄位才畫得出來,停止回報。

**已知的驗證限制**:strict 模式生效後丟棄極為罕見(T5 實測為 0),
因此這段 UI 在正常操作下不易自然觸發。目視確認需要刻意製造一次含壞元素的抽取。
