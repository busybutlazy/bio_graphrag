# Verification Report: structured-outputs-extraction

Plan revision 2,`one-task-at-a-time`。逐 Task 過程見 `TASK_LOG.md`。

## 1. 驗收條件對照

| # | 條件 | 結果 | 證據 |
|---|---|---|---|
| 1 | 一條壞 edge 不再讓整個 chunk 消失 | 通過 | `test_one_bad_edge_does_not_take_the_chunk_with_it`、`test_extract_chunk_salvages_after_the_retry_budget` |
| 2 | 每個丟棄元素都被揭露並計數 | 通過 | `stats.dropped[]` 逐項含 `chunk_id/kind/id/reason`;乾淨執行時計數為 0(見 §3) |
| 3 | 挽救不留懸空邊 | 通過 | `test_an_edge_into_a_dropped_node_is_dropped_too`;反向情形由 `test_an_edge_into_a_never_proposed_node_survives` 守住 |
| 4 | 全部不合格時仍記為失敗 | 通過 | `test_nothing_valid_means_the_chunk_still_fails` |
| 4b | 超過門檻標記 `degraded` 但不阻擋 | 通過 | `test_losing_more_than_half_flags_degraded_without_blocking` |
| 5 | 新欄位與 `docs/api_contract.md` 一致 | 通過 | T4 逐欄位對照(TASK_LOG) |
| 6 | 離線姿態不變 | 通過 | 全部測試在 `-e OPENAI_API_KEY=` 下執行 |
| 7 | 完整離線測試無新失敗;lint/mypy 通過 | 通過 | §4 |
| 8 | 真實抽取:API 接受 strict schema | 通過 | §3 |

## 2. 過程中發現並修正的缺陷(重要)

**首次真實抽取 4 個 chunk 全部失敗。** 錯誤:

```
ValidationError: None is not of type 'object'
On instance['nodes'][0]['properties']: None
```

strict 模式沒有「欄位不存在」這個概念,選用欄位必須宣告且可為 null,模型因此回
`"properties": null`、`"possible_duplicate_of": null`。而內部 schema(依 D2 刻意不動)說
這兩個欄位是 `object` 與 `string`——於是每個節點都不合格、全部被丟棄、每個 chunk 都失敗。

**是本變更引入的缺陷,不是既有問題。** 我把送出去的 schema 改成 nullable,卻沒處理回來的 null。

修正:`strict_schema.drop_strict_nulls()` —— null 是「不存在」的線上形式,進驗證前還原成不存在。
**只剝除選用欄位**:必填欄位為 null 是真的壞掉,必須讓 salvage 丟棄並揭露,不能被悄悄補平。

**為什麼先前的測試沒抓到**:T2/T3 的測試全用手寫的乾淨 candidate,從不含 null。真實 API 輸出才有。
補的四項測試因此**照著真實回傳的形狀**寫(`test_strict_schema.py` 末段),不再用理想化資料。

## 3. 真實抽取前後對照

輸入 `data/private/chapters/endocrine_demo_v1.md`(gitignored),策略 `markdown_header`,4 chunks,
模型 `gpt-4o-mini`。

| 執行 | 時點 | failed_chunks | dropped | tokens |
|---|---|---|---|---|
| 基準(前一變更的紀錄) | prompt 修補後 | 2/4 | 不適用(當時整塊丟棄) | 20808 |
| 本變更第一次 | strict schema,null 缺陷 | **4/4** | 11 nodes / 15 edges | 34020 |
| 本變更第二次 | 重複請求,已中止 | — | — | 見 §5 |
| 本變更第三次 | null 修正後 | **0/4** | **0 / 0** | 18752 |

最終執行:`proposed_nodes: 12`、`proposed_edges: 19`、`proposed_groups: 7`、`degraded_chunks: 0`。

**strict 模式從源頭解決了問題**:沒有任何元素需要被挽救——`dropped` 全為 0。
挽救仍是必要的第二層(模型可以合法輸出 schema 允許、但語意不完整的內容),只是本次沒有用到。

### T1 遺留風險已解除:剝除 `pattern` 後 id 慣例仍被遵守

T1 在極簡 prompt 下觀察到 `n1`、`n2` 這種不合慣例的 id。配上真實 system prompt(規則 11)後,
本次 12 個節點**全部**符合 `<type_prefix>:<snake_case_name>`:

```
concept:homeostasis        system:endocrine_system      structure:endocrine_gland
hormone:insulin            structure:hypothalamus       hormone:adh
structure:kidney           physiological_variable:blood_osmolarity
feedback:blood_osmolarity_negative_feedback
regulatory_effect:adh_decreases_blood_osmolarity
regulatory_effect:adh_increases_blood_volume
misconception:insulin_raises_blood_glucose
```

### Gate 結果:4 pass / 3 fail_pattern

三個失敗都是**模型真的沒給完整結構**,gate 的判斷正確:

- `regulatory_effect:adh_decreases_blood_osmolarity` 缺 `HAS_EFFECT` 入邊
- `regulatory_effect:adh_increases_blood_volume` 缺 `HAS_EFFECT` 入邊
- `feedback:blood_osmolarity_negative_feedback` 缺 `USES_EFFECT` 出邊

這正是專家應該退回的內容,不是本變更的迴歸。

## 4. 自動化檢查

```bash
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
→ 232 passed, 1 failed
```

唯一失敗為既有的 `test_pipeline_run_is_idempotent`:本次真實抽取把 chunks 寫進資料庫,
該測試比對的是 sample 來源的數量。這是已記錄的 volume 狀態 flake,**由跑真實抽取觸發**,非迴歸。

CI 的另外三步(拋棄式容器,釘選 `backend/requirements-dev.txt` 版本,未在 host 安裝):

```
ruff check ...........  All checks passed!
ruff format --check ..  107 files already formatted
mypy .................  Success: no issues found in 83 source files
```

## 5. 一次應揭露的重複花費

第一次真實抽取經由 `POST /admin/ingest/run` 呼叫,**nginx 回 504**(代理讀取逾時;抽取約 4 分鐘)。
後端其實跑完了,但我判讀成請求失敗而重試,**導致第二次抽取同時在跑**。發現後立即重啟 backend 中止,
並把該 job 標記為 `failed`,`error_message` 記明原因。

中止時未寫入 stats,故該次確切 token 數不可考;依執行時間推估約 15–25k。

後續執行改為在容器內直接呼叫 `ingest_document`(與端點相同的程式路徑,不經 nginx),避免重演。
**未修改 nginx 逾時設定**——那是基礎設施變更,不在本變更範圍。

本變更累計花費約 90k tokens(`gpt-4o-mini`):T1 探測 17.9k、失敗執行 34k、中止執行約 15–25k、
成功執行 18.8k。原計畫對 T5 的估計是「約 0.2 美分」,**實際遠高於此**,主因是 null 缺陷與重複請求。

## 6. 一項觀察,非缺陷,需人類決定是否處理

`chunk:001:residual` 這個殘餘組渲染出了一句**完整的 pattern 句子**:
「胰島素 / insulin會造成一個調控效果:使Blood glucose下降。」

原因:該 chunk 引用了**已核准**的 `regulatory_effect:insulin_decreases_blood_glucose` 而未重新提案
(這是被要求的行為),所以切分器找不到可錨定的 RegulatoryEffect 節點,三條邊落入殘餘組,
而渲染器只看邊,就認出了 P1。

`group_statements` 的 docstring 寫著「殘餘組**永不**渲染出 pattern 句子」,守衛測試
`test_a_residual_group_never_renders_a_pattern_sentence` 也在守這件事——但它涵蓋的是
「錨點在場」的情形,涵蓋不到「錨點是既有已核准節點」。

**此行為本身無害甚至正確**:句子與該組內容一致,核准會把三條邊接到既有效果節點上,是想要的結果。
但它與程式碼裡明文的不變式相牴觸,**先於本變更就存在**(切分器只錨定被提案的節點),
只是 strict 模式讓這種 chunk 順利通過才顯現。

兩個處理方向,需 owner 決定,不在本變更範圍:(a) 修正不變式的敘述;
(b) 讓切分器也能錨定「被引用但已核准」的 RegulatoryEffect。

## 7. 未執行

- ~~`make eval`(22 題黃金題)~~:**補記——已由 CI 執行並通過**,見 §8。
- 非 `gpt-4o-mini` 模型、非 `markdown_header` 策略下的行為未評估。
- `refusal` 分支未在真實 API 上觸發過(以假物件單元測試涵蓋);要真的觸發需刻意誘導拒答,
  判斷不值得花費。

## 8. 補記:CI 證據(2026-08-12,PR #20)

本報告 §4、§7 撰寫時分支尚未推送,故無 CI 證據。PR #20 開啟後 CI 已執行,兩個 job 皆通過:

| Job | 結果 | 時間 |
|---|---|---|
| Lint & type-check | pass | 14s |
| Tests & eval (integration) | pass | 1m23s |

Run: https://github.com/busybutlazy/bio_graphrag/actions/runs/31576344848

這補上兩項先前列為未驗證的證據:

1. **乾淨環境複驗**。integration job 在全新 runner 上跑
   `docker compose up -d --build → wait_for_services → make seed → make test → make eval → down -v`。
   §4 提到的 `test_pipeline_run_is_idempotent` **未出現**,證實它確實只是本機 volume 被真實抽取
   寫入所致,非迴歸——先前這是推論,現在是實測。
2. **`make eval` 已執行,22 題黃金題全數通過**(q001–q022,`✅`)。
   §7 原本以「本變更不觸及 retrieval 路徑」為由未執行,那是推論;現在有實測支持。

仍未改變的未驗證項目:`refusal` 分支未在真實 API 觸發、非 `gpt-4o-mini` 與非 `markdown_header`
的行為未評估、單次成功抽取不足以推論常態、中間 commit 未逐一 checkout 測試、
新欄位經由 HTTP 端點的序列化未被實際檢視、`DEGRADED_DROP_RATIO` 未被真實資料觸發過。

## 9. 補記:Task 6 前端揭露(審查 H1 的處置)

審查 H1 指出本報告 §1 的驗收條件 2「每個丟棄元素都被揭露並計數」**只在 API 層成立**:
唯一的人類介面 `renderRunResult` 對新欄位零渲染,被挽救的塊與乾淨的塊在畫面上無法區分。
owner 裁定前端納入本變更(計畫升 revision 3,新增 Task 6)。

**修補後的驗收條件 2 判定**:API 層與人類介面**皆成立**。

驗證(零 token):

- `node --check` 通過。
- 以假造 extractor 產生真的含丟棄的報告,逐一核對前端讀取的每個欄位皆存在且型別正確,
  含 `id: null`(元素本身沒有 id)這個邊界——前端顯示「(無 id)」而非隱藏。
- 完整離線測試 **232 passed**(唯一失敗為既有 volume flake)。

**仍存在的驗證限制**:倉庫沒有前端測試設施,**這段 UI 沒有自動化測試**;
且 strict 模式生效後丟棄極罕見(T5 實測為 0),正常操作下不會自然出現,
目視確認需要刻意製造一次含壞元素的抽取。**「畫得出來」目前只有欄位對照與語法檢查的證據,
沒有人眼看過真實畫面。**
