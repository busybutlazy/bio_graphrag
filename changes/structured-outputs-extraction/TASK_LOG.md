# Task Log: structured-outputs-extraction

Plan revision 2,`one-task-at-a-time`。每個 Task 完成後停止並等待批准。

## Task 1 — strict schema 探測(2026-08-12)

**執行**:拋棄式腳本置於 scratchpad(未進 repo),以唯讀 mount 帶入容器執行:

```bash
docker compose run --rm -v <scratchpad>:/probe:ro backend python /probe/probe_strict.py
```

四個變體,對 `gpt-4o-mini` 各發一次最小請求。schema 無效時 API 在生成前回 400,故被拒的變體幾乎不花錢。

| 變體 | `pattern` | `properties` | 結果 | tokens |
|---|---|---|---|---|
| V1 | 保留 | 自由格式物件 | **拒絕** | 0 |
| V2 | 保留 | 完整列舉 | 接受 | **16795** |
| V3 | 剝除 | 完整列舉 | 接受 | 588 |
| V4 | 剝除 | 剝除 | 接受 | 499 |

**Q1 — strict 接受 `pattern` 嗎?** 接受(V2 通過),**但不能用**。

V2 的輸出顯示模型被 constrained decoding 推進 `^[a-z_]+:` 這段字元類別後開始失控暴衝,
產生 `n_insulin_zhuyinangsu_zhongxin_zhong_zheng_zhongguo_wwnct_waibu_zhongzhuanliufr_...`
這種長到超出截斷顯示的 id,**單次 16795 tokens,是 V3 的 28 倍**。
正則約束在這裡不是免費的保險,是一個會燒錢的陷阱。

→ **決定送出的 schema 剝除 `pattern`。** id 慣例改由既有的兩道內部防線把關:
`extraction_output_schema.json`(內部驗證,不動)與 `engineer_gate._ID_RE`。

**Q2 — strict 接受自由格式 `properties` 物件嗎?** **不接受**。API 明確回:

```
Invalid schema ... In context=('properties','properties','type','0'),
'additionalProperties' is required to be supplied and to be false.
```

→ 送出的 schema 必須**完整列舉**屬性鍵。目前實際被 gate / renderer 讀取的是:
node 的 `interaction_type`、`feedback_type`、`regulated_variable`;edge 的 `trigger_direction`。
這也表示**新增一個節點屬性時,`build_strict_schema()` 的鍵清單必須同步**,否則模型送不出來
——需要一個守衛測試盯住(T2 納入)。

**Q3 — 回應會帶 `refusal` 嗎?** message 物件**有** `refusal` 欄位(本次值為 `None`)。
現行 `llm_client.extract` 直接讀 `message.content`,T2 需處理 `refusal` 非 None 的情況。

**額外觀察(風險,T5 需驗證)**:V3/V4 在**極簡** system prompt 下產出的 id 是 `n1`、`n2`,
不符 `<type_prefix>:<snake_case_name>` 慣例。剝除 `pattern` 後,id 慣例完全依賴 prompt 規則 11。
若模型不遵守,這些節點會在內部驗證被判不合格 → 依 D1 逐元素挽救會被丟棄 → chunk 標記 `degraded`。
行為是誠實的,但可能大量丟棄;T5 的真實抽取必須確認實際 id 仍符合慣例。

**結論**:採 **V3** 形狀 —— strict、剝除 `pattern`、`properties` 完整列舉。

**成本**:合計約 17.9k tokens(`gpt-4o-mini`),其中 16.8k 來自 V2 的暴衝。
略高於計畫估計的「< 1 美分」,實際約 1 美分出頭。

**狀態**:完成,停止等待 T2 批准。

## Task 2 — strict schema 純函式 + llm_client 改用 json_schema(2026-08-12)

**檔案**:

- 新增 `ingestion/extract/strict_schema.py`:`build_strict_schema()` 由
  `schema/extraction_output_schema.json` **執行期推導**(D2),內部 schema 不動。
  剝除 `pattern`(T1 的成本理由)、列舉 `properties` 鍵、選用欄位改為可為 null、
  每個物件補 `required` 全欄位與 `additionalProperties: false`。
- 修改 `ingestion/extract/llm_client.py`:新增 `response_format()` 與 `content_of()` 兩個
  可離線斷言的函式,以及 `LLMRefused`;`extract` 改送 strict json_schema,並在 `refusal`
  非 None 時拋出而不是把它讀成空抽取。
- 新增 `ingestion/tests/test_strict_schema.py`(7 項)、
  `backend/tests/unit/test_property_key_coverage.py`(1 項)。

**一個過程中的修正**:屬性覆蓋守衛原本寫在 `ingestion/tests`,但它需要讀 backend 的
gate/lens 原始碼——**ingestion 不得依賴 backend**(相依方向單向,既有的 anchor 守衛
就是為此放在 backend 側)。已移到 `backend/tests/unit/`,改用 `inspect.getsource` 而非
路徑推導(容器內 `backend/app` 掛載為 `/app/app`,路徑推導本來就會錯)。

**守衛有效性(對照驗證,非裝飾)**:

```
gate/lens 實際讀取的屬性: ['feedback_type','interaction_type','regulated_variable','trigger_direction']
strict schema 宣告的:     ['feedback_type','interaction_type','regulated_variable','trigger_direction']
模擬漏掉 feedback_type -> ['feedback_type']   (非空即代表守衛會失敗)
```

**測試**:`docker compose build backend && docker compose run --rm -e OPENAI_API_KEY= backend
pytest tests ingestion/tests -q` → **217 passed**(T2 前 209,新增 8 項)。未花任何 token。

**狀態**:完成,停止等待 T3 批准。

## Task 3 — 逐元素挽救 + 揭露(2026-08-12)

**檔案**:

- `ingestion/pipeline/validate_extraction.py`:新增 `validate_node` / `validate_edge`。
  以 `{**_schema["$defs"][name], "$defs": _schema["$defs"]}` 組出元素層 schema——`$defs` 必須
  帶著,否則 `#/$defs/node_type` 這類內部參照解不開;組新 dict 不動被快取的 `_schema`。
- 新增 `ingestion/extract/salvage.py`:`salvage(raw) -> Salvaged(candidate, dropped, degraded)`。
  **只丟不修**——補一個 id 或猜一個關係型別,等於把模型從未提出的知識送到專家面前。
- `ingestion/extract/runner.py`:`_extract_chunk` 改回傳 `ExtractionAttempt` dataclass
  (原為 3-tuple),重試用盡後才挽救;`ChunkReport` 新增 `dropped` / `degraded`;
  job `stats` 新增 `dropped_nodes` / `dropped_edges` / `degraded_chunks` / `dropped`(逐項清單)。
- 測試:新增 `ingestion/tests/test_salvage.py`(8 項)、`test_document_ingest.py` 新增 1 項
  DB 實測,並更新既有的 `test_extract_retry_includes_validation_error` 以配合新回傳型別。

**依計畫落實的兩個決定**:

- **D1a 連帶丟棄**:端點指向「本次被丟棄的節點」的邊一併丟棄。關鍵分辨是——端點**從未被提案**
  不算(抽取本來就被要求引用既有概念),只有「提案了又被丟掉」才連帶。搞混會刪掉正確的邊。
- **D1b 只揭露不擋**:丟棄比例 > `DEGRADED_DROP_RATIO`(0.5)時標記 `degraded`,照常進佇列。

**重試優先於挽救**:挽救只在重試用盡後執行。修正後的完整答案優於修剪過的答案,因為挽救會丟掉的
那個元素,往往正是該 chunk 真正要講的東西。有測試釘住(`salvage 不得短路重試`)。

**U4 冪等已證明**(`test_a_re_run_supplies_what_salvage_had_to_drop`):
第一次抽取的方向邊缺 `id` → 被丟棄、chunk 未失敗、gate 對該組判 `fail_pattern`;
修好後重跑 → 補進**同一組**(group_id 由 chunk + anchor 推導,不會另開新組)→ gate 轉 `pass`。
若非如此,被丟棄的元素將無法回收,只能手動清佇列。

**測試**:`docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`
→ **229 passed**(T3 前 217,新增 12 項)。未花任何 token。

**狀態**:完成,停止等待 T4 批准。

## Task 4 — 契約文件同步(2026-08-12)

**發現的既有缺口**:`/admin/ingest/*` 三個端點在 `docs/api_contract.md` **完全沒有專屬章節**,
只在第 252 行被順帶提及。新增章節時已把這個缺口明寫出來,但**沒有**順手補寫整個 ingest 契約
(請求形狀、雙重 gate)——那超出本變更範圍。

**新增** `### POST /admin/ingest/run —— 部分接受與丟棄揭露`,記載:

- 行為改變:一個 chunk 從「全有全無」改為「部分接受」;挽救**只丟棄不修補**;
  存活元素不因此免除任何檢查(少方向邊的三段式仍判 `fail_pattern`)。
- `stats` 四個新欄位(`dropped_nodes` / `dropped_edges` / `degraded_chunks` / `dropped`)
  與 `chunks[]` 的 `dropped` / `degraded`,含型別與語意。
- 三點易誤解處:連帶丟棄的判準(提案過才連帶,從未提案不算)、`degraded` 只揭露不擋、
  全部不合格時仍計入 `failed_chunks`。
- 丟棄非永久損失:修正後重跑補進同一組。

**逐欄位對照實作**(不靠人眼):

```
dropped 形狀: [{"kind":"node","id":"hormone:bad","reason":"'label' is a required property"},
              {"kind":"edge","id":"e1","reason":"端點已被丟棄:hormone:bad"}]
degraded: True
ChunkReport 欄位: [... 'dropped', 'degraded', ...]
```

與文件所載一致。

**CI 檢查**(拋棄式容器,釘選 `backend/requirements-dev.txt` 版本,未在 host 安裝):

```
ruff check ...........  All checks passed!
ruff format --check ..  107 files already formatted（先修正了 3 個新測試檔的格式）
mypy .................  Success: no issues found in 83 source files
```

**測試**:**229 passed**(未變動,T4 只動文件與格式)。未花任何 token。

**狀態**:完成,停止等待 T5 批准(T5 需批准真實抽取的 token 花費)。

## Task 5 — 完整驗證(2026-08-12)

詳見 `VERIFICATION_REPORT.md`。摘要:

- 首次真實抽取 **4/4 chunk 全失敗** —— 本變更引入的缺陷:strict 模式的選用欄位回傳 `null`,
  而內部 schema 不接受 null。修正為 `strict_schema.drop_strict_nulls()`,並補四項
  **照真實回傳形狀**撰寫的測試(先前測試全用手寫乾淨資料,結構上抓不到)。
- 修正後重跑:**failed_chunks 0/4、dropped 0/0**、12 nodes / 19 edges / 7 groups、18752 tokens。
  strict 模式從源頭消除了問題,挽救本次未動用。
- T1 遺留風險解除:剝除 `pattern` 後,12 個節點 id **全部**符合慣例。
- Gate:4 pass / 3 fail_pattern,三個失敗都是模型真的缺邊,判斷正確。
- 測試 **232 passed**,唯一失敗是由跑真實抽取觸發的既有 volume flake;
  ruff check / ruff format --check / mypy 全過。
- **應揭露**:nginx 504 導致我重試,造成一次重複抽取(已中止並標記);
  本變更累計約 90k tokens,遠高於計畫對 T5 的估計。
- 一項觀察待 owner 決定:殘餘組在「錨點為既有已核准節點」時會渲染出 pattern 句子,
  與程式碼明文的不變式牴觸,但行為本身正確且先於本變更存在。

**狀態**:完成。五個 Task 全部結束,交由獨立審查。未 commit(依 Execution Policy,
commit/push 需另行批准)。
