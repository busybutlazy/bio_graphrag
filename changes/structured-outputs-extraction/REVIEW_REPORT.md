# Review Report: structured-outputs-extraction

## Review Context

- **Diff base and scope**:`git diff main...HEAD`,`main` (`c292a68`) → `feat/structured-outputs-extraction` (`15baf18`),
  14 檔 +1548 / −22。其中程式碼變更全數落在前三個 commit(`51a2056`、`521197c`、`a286806`),
  後兩個 commit(`0d61550`、`15baf18`)只動 `changes/` 底下的報告。
  變更報告自述的「13 檔 +1361/−22」是對 `a286806` 而言,**已核對相符**
  (`git diff main...a286806 --stat` → `13 files changed, 1361 insertions(+), 22 deletions(-)`)。
- **Artifacts reviewed**:`IMPLEMENTATION_PLAN.md`(revision 2,Approved)、`TASK_LOG.md`、
  `VERIFICATION_REPORT.md`、`CHANGE_REPORT.md`、`docs/notes.md` 的 N1(需求來源)、
  全部程式碼與測試 diff、`schema/extraction_output_schema.json`、`docs/api_contract.md`、
  `backend/app/api/routes_ingest.py`、`frontend/app.js`、`.github/workflows/ci.yml`、
  CI run 31576344848、PR #20。
- **Independence disclosure**:本次審查在**獨立 session** 進行——實作 commit 的 trailer 為
  `session_01CJ9gSma26bWd1QsFrGndEg`,本 session 為 `session_01GP9o3FKphK5pnRaF9t1g4L`,
  審查者未持有實作過程的對話脈絡,所有結論由 repo 內的產出物與實測重建。
  但仍為**同一個 agent 家族、共用同一份專案記憶**,不等同於人類獨立審查;
  下列 High/Medium 事項與兩項程序偏差**必須由人類裁定**。
- **審查者實際執行的檢查**(唯讀 / 既有容器入口 / 零 token 花費):
  - `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`
    → **1 failed, 232 passed**,唯一失敗為 `test_pipeline_run_is_idempotent`
    (`chunk_count 12 != 9`),與 `VERIFICATION_REPORT.md` §4 所述**逐字相符**,
    且與已記錄的 volume flake 一致。
  - 容器內對 `build_strict_schema` / `drop_strict_nulls` / `salvage` 的四組對抗性探測(見下)。
  - `gh run view 31576344848` → 兩個 job 皆 `success`,`headSha = 0d61550`。
    該 sha 之後只有一個純文件 commit,**CI 證據涵蓋全部程式碼變更**,此點成立。

## Completion Claim Assessment

**主要完成宣稱成立,但「揭露」這項核心宣稱只到 API 層,未到人類看得到的地方。**

八項驗收條件我逐條追到實作與測試,其中 AC1、AC3、AC4 我另以自寫探測獨立複現(下表)。
測試數字、CI 結果、diff 統計、契約文件欄位對照,查核後與報告一致,**未發現誇大或無據的陳述**。
變更報告主動揭露了三項對自己不利的事實(路徑偏離未停止、一次重複的付費抽取、成本遠超估計),
這部分的誠實度符合本專案的治理要求。

但有一項落差報告沒有講:本變更在 `runner.py:49-50` 自述「揭露就是全部的重點——部分接受卻不說
自己掉了什麼,就是靜默資料遺失」,而**唯一的人類操作介面 `frontend/app.js::renderRunResult`
完全沒有渲染任何一個新欄位**。前端在計畫中被明確列為 Out of Scope 且經批准,所以這不是違反計畫;
但它使本變更的招牌性質在成品上未能端到端成立,而報告沒有點出這件事(見 High 1)。

另外兩項為程序問題,已由實作者自行揭露,審查者確認屬實並交人類裁定:
新增 `backend/tests/unit/` 路徑時未依 Execution Policy 停止、以及 nginx 504 誤判造成的重複抽取。

## Findings

### Blocking

無。沒有發現會讓未經核准的知識進入 `approved` 圖譜、破壞既有契約、或造成資料損毀的缺陷。
`schema/extraction_output_schema.json` 確認**逐字未改**,`engineer_gate` 對人工提案的行為不受影響。

### High

**H1 — 新的揭露欄位在前端一個都沒有顯示,部分接受對操作者而言是靜默的**

- **證據**:`frontend/app.js:1167-1199`(`renderRunResult`)。tiles 只讀
  `s.chunks / s.proposed_nodes / s.proposed_edges / s.failed_chunks / s.tokens`;
  逐塊卡片只在 `ch.extraction_failed` 為真時顯示「⚠ 此塊抽取失敗」,否則渲染 proposed id chips。
  `grep -rn "dropped\|degraded" frontend/` **零命中**。
- **違反的要求**:`runner.py:49-50` 與 `docs/api_contract.md` 新增節所宣示的揭露原則;
  以及專案的稽核治理主軸(所有損失必須對人類可見)。
- **影響**:本變更把「一個元素壞掉 → 整塊失敗(UI 有紅色警告)」改成
  「一個元素壞掉 → 靜靜丟掉、其餘照常入列」。在 `/app/` 匯入頁上,一個被挽救的 chunk
  與一個完全乾淨的 chunk **視覺上完全一樣**;`failed_chunks` 這個唯一有 UI 呈現的訊號
  在新行為下會系統性低報。變更報告只寫「依賴 `failed_chunks` 的既有流程或人工習慣需改看
  `dropped_*`」,**沒有指出本專案自己的 UI 就是這樣一個消費端,且未同步**。
  真實抽取 `dropped` 為 0,所以這個落差在 T5 不會顯現——它會在第一次真的丟東西時才發作。
- **修補方向(界定)**:二選一,由人類決定——(a) 開一個後續 change 在 `renderRunResult`
  補上 `dropped_nodes` / `dropped_edges` / `degraded_chunks` tile 與逐塊的丟棄清單,
  合併前先擋著;(b) 若接受先合併,則在 `CHANGE_REPORT.md` 的〈Remaining Work〉明寫
  「揭露目前只到 API 回應,產品 UI 尚未呈現」,不要讓下一個讀報告的人以為揭露已經完成。
  審查者不做這個取捨。

### Medium

**M1 — 連帶丟棄(D1a)只在 chunk 內生效,契約文件的措辭讀起來像整次執行**

- **證據**:`salvage.py:58,76-81` —— `dropped_node_ids` 是 `salvage()` 單次呼叫的區域變數,
  作用域等於一個 chunk;`runner.py:273` 每個 chunk 各自呼叫。
  `docs/api_contract.md` 寫的是「端點指向『**本次**被提案、但已被丟棄』的節點」,
  「本次」在該段落沒有界定是 run 還是 chunk。
- **風險**:同一次執行中,chunk 1 的節點 `hormone:x` 被丟棄,chunk 3 又輸出一條指向
  `hormone:x` 的邊(模型跨 chunk 重複使用同一個 id 是可能的,尤其 `hormone:insulin`
  這類核心概念)。該邊在 chunk 3 被視為「端點從未被提案」而**存活**,於是產生一個
  D1a 本來要消滅的懸空邊。
- **影響**:有界。`approve_group` 會在核准時擋下
  (`service.py:481` 註記「every edge endpoint is either proposed in this group or already
  approved (409)」),所以結果是**該組無法核准、浪費專家時間**,不是圖譜被污染。
  現有測試(`test_an_edge_into_a_never_proposed_node_survives`)只涵蓋單 chunk,
  跨 chunk 這條路徑沒有測試。
- **修補方向**:最小做法是把契約文件與 `salvage.py` 的註解明確寫成「chunk 範圍內」,
  並在〈Known Limitations〉列出跨 chunk 殘留;若要真的關掉,需把 dropped id 提升到
  `ingest_document` 層累積——那是行為擴大,應另立 change 而非在本次補。

**M2 — 送給模型的 schema 額外剝除了所有 `description`,程式碼給的理由與證據不符,且三份報告都沒提**

- **證據**:`strict_schema.py:38` —— `_DROPPED_KEYWORDS = ("pattern", "description")`,
  上一行註解寫「Dropped for cost, not for support — see the module docstring」。
  但模組 docstring 明列的是「**兩項**偏離」,只講 `pattern` 與 `properties` 列舉,
  **完全沒有提到 `description`**。`TASK_LOG.md` Task 1/2、`CHANGE_REPORT.md`
  §Observable Behavior 1、`docs/api_contract.md` 新增節,三處描述送出的 schema 時
  一律寫「剝除 `pattern`、列舉 `properties` 鍵、選用欄位可為 null」,同樣沒有這一項。
- **問題**:(a) T1 的四個探測變體只比較了 `pattern` 的有無,**沒有任何一個變體測過
  `description` 的成本影響**,所以「Dropped for cost」這個註解是沒有證據支撐的斷言;
  (b) 被剝掉的包含 `source`/`target` 的「來源節點 id / 目標節點 id」與
  `possible_duplicate_of` 的用途說明——而本專案觀察到的抽取品質問題正是**邊的方向**。
  Structured Outputs 的 `description` 是模型可讀的欄位級指示,丟掉它是放棄一個免費的槓桿。
- **影響**:不是相對於 `main` 的迴歸(`main` 用 `json_object`,根本沒送 schema),
  但它是一個**未揭露的送出內容差異**。任何人想從報告重建「我們到底送了什麼給模型」都會得到錯的答案。
- **修補方向**:擇一——把 `description` 從 `_DROPPED_KEYWORDS` 拿掉(需一次付費驗證,
  不能憑推測),或保留剝除但把註解與三份文件的敘述改成事實,並說明理由是
  「未經測試的成本疑慮」而非既有證據。兩者都不該由審查者代做。

**M3 — 屬性覆蓋守衛的比對方式脆弱,而它擋的正是「不會出聲」的失敗**

- **證據**:`backend/tests/unit/test_property_key_coverage.py:20-27`。
  `_keys_read` 只在含 `props` 或 `"properties"` 的行上,用 `r'\.get\("(\w+)"\)'` 抓鍵名。
  這個正則要求 `)` 緊接在引號後,因此 `.get("key", default)` 抓不到;
  下標存取也抓不到——`back_translation.py:120` 的 `props[lid]["feedback_type"]`
  現在就是隱形的(只因為同一個鍵在 `:114` 另有 `.get()` 寫法,守衛才碰巧沒漏)。
- **影響**:守衛自己的 docstring 說得很準確——漏一個鍵是「invisible rather than loud」:
  模型結構上送不出該屬性,抽取看起來很聽話,專家永遠看不到那個 antagonism 標記。
  一次把 `.get("x")` 改寫成 `.get("x", "")` 或下標的無辜重構,就會讓守衛靜靜失效,
  而測試仍然是綠的。`assert read` 只保證「抓到了某些東西」,不保證抓全。
- **修補方向**:改用 AST 走訪(`ast.walk` 找 `Subscript` 與 `Call(attr='get')` 的字串常數),
  或退一步:把四個鍵集中成一份 backend 側的常數,讓 gate/lens 從那裡讀,
  守衛改比對常數而非掃原始碼。屬於後續 change,不建議在本次修。

### Low

**L1 — `salvage` 會靜靜吃掉頂層的未知欄位,且不計入 `dropped`**

實測(審查者探測 D):`{"nodes": [...], "edges": [...], "notes": "x"}` 在
`validate_extraction_output` 下是 `ValidationError`(頂層 `additionalProperties: false`),
但 `salvage()` 只讀 `nodes`/`edges` 重組,結果**通過、`dropped` 為空**。
strict 模式下模型送不出多餘的頂層鍵,所以現階段實務上到不了;
但它意味著「舊行為會失敗的輸入,新行為會成功且不揭露」——與本模組的揭露原則不一致。
修補方向:重組後對成品再跑一次 `validate_extraction_output`,或把未知頂層鍵記進 `dropped`。

**L2 — `dropped[].reason` 與 `stats.dropped` 沒有長度上限**

`salvage.py:65,74` 直接放 `jsonschema` 的 `exc.message`,該訊息在
`additionalProperties` 類錯誤下會內嵌整個 instance。這份 list 會整包寫進
`ingestion_jobs.stats` 的 JSON 欄位並回傳給呼叫端。沒有截斷、沒有筆數上限。
不構成新的機敏外洩(chunk 原文本來就在同一份回應的 `content` 裡),但一個
大量丟棄的 job 會產生異常肥大的 stats 列。修補方向:reason 截斷至固定長度、
`dropped` 設上限並附「另有 N 筆」計數。

**L3 — strict schema 每次呼叫都重讀磁碟上的 schema,與內部驗證的快取不同步**

`strict_schema.py:80,124` 每次 `build_strict_schema()` / `_optional_keys()` 都
`SCHEMA_PATH.read_text()` + `json.loads`(`drop_strict_nulls` 每個 candidate 讀兩次),
而 `validate_extraction.py:7` 是 **import 時快取一次**。若有人在一個 job 執行中修改該檔,
同一次執行的不同 chunk 會用到不同版本的 schema 去推導、卻用舊版去驗證。
機率極低但診斷起來會很痛。另 `build_strict_schema` 的 `copy.deepcopy` 對
`json.loads` 的新物件是多餘的。修補方向:與 `validate_extraction` 一致地在模組層讀一次。

**L4 — `degraded` 只有單元層測試,端到端與真實資料都沒碰過**

`test_losing_more_than_half_flags_degraded_without_blocking` 驗的是 `salvage()` 的回傳值;
`stats["degraded_chunks"] >= 1` 這條路徑(`runner.py:291`)沒有任何測試覆蓋——
唯一的 DB 實測 `test_a_re_run_supplies_what_salvage_had_to_drop` 斷言的是 `== 0`。
`DEGRADED_DROP_RATIO = 0.5` 從未被真實資料觸發(變更報告已自述)。
影響:這個門檻與計數器目前只有「寫對了」的證據,沒有「跑起來會動」的證據。

**L5 — 變更報告的比較基準已過期**

`CHANGE_REPORT.md:3` 寫「→ `a286806`,三個 commit」,但分支頭是 `15baf18`(五個 commit)。
CI 補記是後來追加的,標頭沒跟著更新。數字本身正確(見 Review Context),純屬追溯性瑕疵。

### Suggestion

**S1 — 被挽救的 chunk 丟失了觸發挽救的那個整包錯誤**

`runner.py:176` 在挽救成功時回傳 `error=None`,於是 `stats.extraction_errors` 不會有這個 chunk。
逐元素的 `reason` 保留了,但「重試兩次都失敗、最後那次的整包驗證錯誤是什麼」被丟掉了。
在診斷「為什麼模型一直送出壞東西」時,那個錯誤原文比逐元素理由更有訊息量。
建議把 `last_error` 一併帶進 `ExtractionAttempt` 並在報告中以獨立欄位呈現(不改既有欄位語意)。

**S2 — `_drop` 允許非字串的 `id` 進入揭露清單**

`salvage.py:36-37` 直接 `element.get("id")`,型別未約束;`docs/api_contract.md` 只說
「`id` 可能為 `null`」。strict 模式下實務上只會是字串或缺席,屬防禦性建議。

## Requirement and Test Coverage Gaps

| AC | 判定 | 審查者的獨立證據 |
|---|---|---|
| 1 一條壞 edge 不再帶走整個 chunk | **成立** | 探測 C:壞 node + 兩條邊 → 存活 `e2`,`candidate` 非 None;另有 2 項單元測試 |
| 2 每個丟棄元素都被揭露並計數 | **API 層成立,人類介面不成立** | `stats.dropped` 形狀正確;前端零渲染 → **H1** |
| 3 不留懸空邊 | **chunk 內成立** | 探測 C:指向被丟棄節點的 `e1` 連帶丟棄;跨 chunk 未涵蓋 → **M1** |
| 4 全部不合格仍記為失敗 | **成立** | 探測 B:`label: null` → `candidate is None`,連帶邊也被揭露 |
| 4b 超門檻標記但不擋 | **單元層成立,端到端未測** | → **L4** |
| 5 新欄位與契約文件一致 | **成立,且比報告所述更強** | 逐欄位比對 `runner.py:346-371` 與文件表格,四個 stats 欄位 + `chunks[].dropped/degraded` 全數相符。變更報告擔心「經 HTTP 端點的序列化未被檢視」——審查者確認 `routes_ingest.py:169` 的回傳型別是裸 `dict`、無 `response_model` 過濾,`asdict()` 的欄位會原樣輸出,**殘餘風險比報告自評的低** |
| 6 離線姿態不變 | **成立** | 全套測試在 `-e OPENAI_API_KEY=` 下 232 passed;`llm_client.is_configured()` 為唯一入口 |
| 7 完整離線測試無新失敗 + lint/mypy | **成立** | 本機複現 232 passed / 1 known flake(數字與報告逐字相符);CI 兩個 job 綠,涵蓋全部程式碼 commit |
| 8 真實抽取接受 strict schema | **成立但不可複驗** | 依賴單次付費執行的紀錄,審查者未花 token 複驗;樣本數 1,報告已自述 |

**未被任何測試覆蓋的行為**:跨 chunk 的懸空邊(M1)、`stats["degraded_chunks"]` 非零路徑(L4)、
頂層未知鍵的靜默剝除(L1)、`/admin/ingest/run` 端點層的實際 JSON 輸出(以程式碼推論確認,無測試)。

## Compatibility, Security, and Scope Assessment

- **相容性**:對外只增欄位,既有欄位未改名未改語意——核對 `runner.py` 的 stats 組裝後確認。
  內部破壞性變更(`_extract_chunk` 3-tuple → `ExtractionAttempt`)限於模組私有函式,
  呼叫端我另行 `grep` 複查,只有 `ingest_document` 與兩個測試檔,皆已更新。
  **行為相容性的實質變化在 `failed_chunks` 的語意**:同一個輸入,新舊版本的這個數字會不同。
  這一點報告有講,但如 H1 所述,唯一的消費端沒有跟上。
- **安全**:未新增輸入路徑,未動 `/admin` 雙重 gate,未動 `status='approved'` 的檢索不變式。
  挽救後的元素**照常**進入 Schema gate 與專家 gate——T5 實測 7 組中 3 組被判 `fail_pattern`,
  證明存活不等於放行,這是本變更最重要的安全性質,成立。
  新資料流只有「錯誤訊息 → stats JSON → API 回應」,而 chunk 原文本就在同一份回應中,無新增曝露面。
  唯一的量級問題是 L2(無上限)。
- **Schema / migration / dependency**:確認皆為零。`extraction_output_schema.json`
  在 diff 中未出現;無新增套件;無 DB 結構變更。
- **範圍**:14 個檔案中 13 個落在批准路徑內。`backend/tests/unit/test_property_key_coverage.py`
  在批准路徑外——**實作者已自行揭露**,理由(ingestion 不得依賴 backend)技術上正確,
  檔案本身無害。但依 Execution Policy,新增路徑是 mandatory stop condition,當時未停止。
  **這需要人類追認,不是審查者能核准的事。**
- **未追蹤產出物**:`changes/structured-outputs-extraction/PR_DRAFT.md`、
  `changes/extraction-prompt-inline-pattern-rules/PR_DRAFT.md`、`docs/notes.md` 三個檔案
  目前是 untracked。其中 `docs/notes.md` 是本變更的**需求來源(N1)**卻不在版控中,
  意味著離開這台機器就無法重建原始請求。建議人類決定是否納管。

## Unreviewed Areas and Residual Risk

- **真實 API 行為**:審查者未花任何 token。strict schema 被接受、id 慣例在剝除 `pattern`
  後仍被遵守、`refusal` 分支——全部只有實作者單次執行的紀錄,審查者無法獨立複驗。
- **核准之後的下游**:被挽救的提案經 `approve_group` 寫入 Neo4j 的完整路徑未實測
  (只讀了 `service.py` 的守衛註記)。M1 的影響評估建立在該守衛如註記所述運作之上。
- **前端**:只檢查了 `renderRunResult` 與 `renderPreview` 相關段落,其餘未看。
- **非 `gpt-4o-mini` 模型、非 `markdown_header` 策略、多 job 併發**:完全未評估。
- **`VERIFICATION_REPORT.md` §6 的殘餘組觀察**(錨點為既有已核准節點時會渲染出 pattern 句子):
  審查者確認這確實**先於本變更存在**、不是迴歸,但也確認它與 `group_statements` 的
  docstring 明文不變式相牴觸。維持實作者的判斷:交 owner 決定,不屬本變更。
- **殘餘風險總結**:最大的一項不是程式缺陷,而是 H1——本變更把失敗模式從「大聲」改成「安靜」,
  而讓它重新變大聲的那一半(UI)不在批准範圍內。第二大的是 M2 揭示的落差:
  「我們送給模型的到底是什麼」目前在文件上是不完整的。

## Human Disposition Required

需要人類裁定的事項,依序:

1. **H1**:是否在合併前補上前端揭露,或接受先合併並把落差寫進〈Remaining Work〉。
2. **路徑偏離**:`backend/tests/unit/test_property_key_coverage.py` 的事後追認
   (Execution Policy 的 stop condition 當時未被遵守)。
3. **重複的付費抽取**:約 15–25k tokens 的浪費,已揭露、job 已標記 `failed`,是否需要後續處置。
4. **M1 / M2 / M3**:分別決定「現在修」「開後續 change」或「記入已知限制」。
5. **`docs/notes.md` 等未追蹤檔案**是否納入版控。

The reviewer does not approve, fix, merge, or release this change.
