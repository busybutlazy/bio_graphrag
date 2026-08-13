# Review Report: close-approve-item-backdoor

## Review Context

- **Diff base and scope**:`main` @ `8112fda` → 目前**工作區**(未 commit)。
  `git diff main...HEAD` 為空,`git diff` 顯示 7 個檔案(`CLAUDE.md`、
  `backend/app/api/routes_curation.py`、`backend/app/curation/service.py`、
  `backend/app/schemas/curation.py`、`backend/tests/integration/test_curation.py`、
  `docs/api_contract.md`、`docs/notes.md`),另有未追蹤的 `changes/close-approve-item-backdoor/`。
  **被審查的狀態沒有 commit 釘住**——本報告的引用對應到 2026-08-13 審查當下的工作區內容。
- **Artifacts reviewed**:`IMPLEMENTATION_PLAN.md`(rev 1,Approved / jett / 2026-08-13,
  medium / `supervised-auto`,D1–D4 決議齊備)、`TASK_LOG.md`、`VERIFICATION_REPORT.md`、
  `CHANGE_REPORT.md`、完整 diff、`test_review_groups.py`、`test_curation.py`、
  `routes_*.py` 全部寫入路由、`README.md`、`docs/graph_plan.md`。
- **Independence disclosure**:本次審查在**獨立 session** 進行,未參與規劃或實作,
  未讀取實作 session 的上下文,僅以 repo 內產出物與程式碼為依據。
  未執行任何容器命令(下述結論皆可由 diff 與 grep 機械複核),亦未修改任何實作檔。
  **唯一寫入為本報告。**

## Completion Claim Assessment

宣稱為「9 條 AC 全部通過、無迴歸、無偏差」。**核心的三條(AC1–AC3,後門關閉)成立**,
但**AC8(文件與實作一致)不成立**,且 `CHANGE_REPORT.md` §5「偏差:無」因此不準確。

逐條複核:

| AC | 宣稱 | 本次複核 | 結論 |
|---|---|---|---|
| AC1 | approve 端點不存在 | diff 確認 `@router.post(".../approve")` 已刪除;`grep "@router.post"` 全 repo 只剩 12 條,無此路徑 | **成立**(但引用的 404 證據本身不充分,見 M1) |
| AC2 | `POST /curation/items` 不存在 | 同上;該路徑僅剩 `GET`,故 405 正確 | **成立** |
| AC3 | reject 端點不存在 | 同上 | **成立**(同 M1) |
| AC4 | `GET` 仍可用 | 路由與 `list_items` 逐字未動 | **成立** |
| AC5 | 群組路徑一行未改 | `git diff` 不含 `test_review_groups.py` / `test_curation_groups.py` / 群組 service 函式 | **成立** |
| AC6 | 不變式仍有測試守著 | `test_proposed_statement_reaches_the_graph_only_after_approval` 確實驗了 propose → 查無 → approve → `status='approved'`,**比原測試強** | **成立** |
| AC7 | 無孤兒程式碼 | `_load_json`、`anyio`、`json`、`load_neo4j`、`_validate_curation_payload`、`ApproveRejectRequest`、`CurationItemResponse`、`_fetch_change_log`、`asyncio` 全部仍有使用者(逐一 grep 確認) | **成立** |
| AC8 | 文件與實作一致 | **`README.md:117-125` 仍以 curl 教讀者呼叫兩個已移除的端點**;`docs/graph_plan.md:362-364` 的 API 表仍列出三者 | **不成立(H1)** |
| AC9 | 無迴歸,測試數對得上 | 242 − 2 + 1 = 241 的算式與檔案內測試數(5 → 4)一致,可自洽;基準 flake 與 memory 記載的既有 flake 相符 | **成立(算式自洽,未重跑)** |

`VERIFICATION_REPORT.md` 對 AC8 打 ✅ 是**未經檢查的宣稱**——它只核對了 Plan 點名的三份文件,
沒有對 repo 做一次「還有誰在講這三個端點」的全域搜尋。

值得肯定的是:報告在 L1/R4 主動要求審查者自行核對「移除的兩個測試是否真有等價覆蓋」。
**本次核對結果:等價成立**(見〈Requirement and Test Coverage Gaps〉)。這種可反證的自我揭露是對的。

## Findings

### Blocking

無。後門本身確實關閉,無資料風險、無 schema 變更、可完全 revert。

### High

**H1 — `README.md` 仍教讀者呼叫已移除的端點;AC8 不成立,`CHANGE_REPORT.md`「偏差:無」不準確。**

- **證據/位置**:`README.md:115-125`
  ```bash
  curl -X POST http://localhost:8080/admin/curation/items \
    -d '{"item_type":"node",...}'
  curl -X POST http://localhost:8080/admin/curation/items/curation:hormone:example/approve \
    -d '{"reviewer":"you","reason":"looks correct"}'
  ```
  前一行緊接著寫「New nodes/edges go through human curation first」——
  **這正是本變更要推翻的敘述**:那條路徑不但不再存在,它當初根本沒有過任何 gate。
  次要位置:`docs/graph_plan.md:362-364`(§5.2 API 表)仍列出三個端點;
  `CLAUDE.md` 稱 `graph_plan.md` 為「authoritative design docs」之一。
- **違反的要求**:AC8「文件與實作一致」;`CHANGE_REPORT.md` §5「偏差:無」;
  Plan〈In Scope〉的「文件同步」只列了三份檔案,**掃描面本身就不完整**,
  而 T3 的 stop condition(「若發現文件所述與實作不符,以實作為準並回報差異」)未被觸發,
  因為沒有人去看 README。
- **影響**:README 是這個履歷專案的**對外門面**。照著複製的人會拿到 `405` 與 `404`,
  且會建立一個錯誤的心智模型——以為單項核准是這個系統的治理流程,
  而整個變更的論述正好相反。這比程式碼問題更傷:它讓治理論述在最多人讀到的地方是錯的。
  `graph_plan.md` 的傷害較輕(它是階段計畫書,寫的是「第一階段」的規劃),但它被 `CLAUDE.md` 點名為權威文件。
- **修補方向(有界)**:把 `README.md` 那兩個 curl 換成群組路徑
  (`POST /admin/curation/groups` → `POST /admin/review/groups/{id}/approve`),
  並修掉其上下文那句敘述;`graph_plan.md` §5.2 就地標注「已由群組端點取代」而非刪除
  (它是歷史計畫書,改寫會失去記錄價值)。**兩者都在 Plan 已批准路徑之外,需人類先決定是否擴大範圍。**
  修完後 AC8 與 `CHANGE_REPORT.md` §5 需一併更正。

### Medium

**M1 — 「後門不存在」的守衛測試對三條路徑中的兩條是**同義反覆**,擋不住它宣稱要擋的回歸。**

- **證據/位置**:`backend/tests/integration/test_curation.py:120-142`
  ```python
  ("/admin/curation/items/whatever/approve", {"reviewer": "x"}),
  ("/admin/curation/items/whatever/reject",  {"reviewer": "x"}),
  ...
  assert resp.status_code in (404, 405)
  ```
  對照被移除的實作(diff 中的 `approve_item` / `reject_item`):
  ```python
  if row is None:
      raise CurationError(404, f"curation item {item_id} not found")
  ```
  **端點存在但 `item_id` 不存在時,回的也是 404。** 因此對 approve/reject 兩條路徑,
  這個斷言在「路由已移除」與「路由被加回來了」兩種世界裡**結果完全相同**。
- **違反的要求**:測試自身的 docstring 宣稱
  「Anyone re-adding these routes for convenience has to make this test fail first」——
  對 3 條路徑中的 2 條**不成立**。連帶地,
  `VERIFICATION_REPORT.md` §3 標題為「後門不存在的直接證據」的那三行 curl,
  其中 `-> 404` 的兩行同樣**不具鑑別力**(405 那行有效,因為 405 只可能來自「路徑只註冊了 GET」)。
- **影響**:AC1/AC3 的**結論仍然正確**(由 diff 與 `grep "@router.post"` 機械確認,無此路由),
  但**守門機制是假的**。這正是 `CHANGE_REPORT.md` L4 想處理卻沒處理到的情境:
  日後有人「為了方便」把 `approve_item` 加回來,CI 會綠燈通過。
  對一個以治理為賣點的專案,一個看起來在守門、實際上不守的測試,比沒有測試更糟。
- **修補方向(有界)**:改為斷言**路由本身不存在**,而非斷言狀態碼。例如以
  `{r.path for r in app.routes}` / `app.openapi()["paths"]` 檢查
  `"/admin/curation/items/{item_id}/approve"` 不在其中;
  或先用群組端點建立一筆真實的 `proposed` 列,再對它發 POST——
  端點若存在會回 200/409,不會回 404。任一種都能恢復鑑別力,且都只動 `test_curation.py`(已在批准路徑內)。

### Low

**L1 — 新測試在 `graph_change_logs` 留下每次執行一筆的殘留,原測試不會。**

- **證據/位置**:`test_curation.py:41-43` 的 autouse 清理是
  `DELETE FROM graph_change_logs WHERE target_id LIKE '%test_curation%'`;
  但 `approve_group` 寫的稽核列是 `target_id=group_id`(`service.py:541`),
  而 `create_group` 產生的是 `group:human:<uuid4>`(`service.py:212`)——**不含 `test_curation`,清不掉**。
  (`curation_items` 那半清得掉:item_id 是 `curation:{group_id}:{elem_id}`,含節點 id 中的 `test_curation`。)
  舊的 `test_approve_writes_to_neo4j_and_logs_change` 記的 `target_id` 是節點 id,會被清掉。
- **影響**:每跑一次測試,稽核表多一筆 `actor='test_reviewer'` 的 approve 列。
  目前 `graph_change_logs` **沒有任何端點或前端會讀**(已 grep 確認),所以不影響展示;
  但這正是本專案已知 flake(`test_pipeline_run_is_idempotent`,非乾淨 volume)的同一類殘留,
  在稽核表上累積尤其諷刺。
- **修補方向(有界)**:在該測試的 `finally` 內一併刪除 `target_id = group_id` 的稽核列,
  或把清理條件放寬到涵蓋測試建立的 group。僅動 `test_curation.py`。

**L2 — AC1/AC2 的字面條件(`grep` 無命中)未達成,驗證報告靜默改寫了判準。**

- **證據/位置**:Plan AC1「`grep -rn "approve_item" backend/app` **無命中**」;
  實際 `backend/app/curation/service.py:119-125`、`routes_curation.py:4-8`、
  `schemas/curation.py:12` 都寫了說明性註解,含這些名字。
  `VERIFICATION_REPORT.md` 把判準記為「`grep` 僅命中說明性註解」。
- **影響**:實質意圖(無**程式碼**參照)確實達成,且驗證報告**有誠實寫出實際的 grep 結果**,
  不是隱瞞。但 AC 的字面條件被就地改寫而未標為偏差。註解本身是好的
  (T1 明確要求寫下「為什麼這條路徑不存在」),問題只在 AC 措辭與證據沒有對齊。
- **修補方向**:在 `CHANGE_REPORT.md` §5 以一行記為「AC 措辭偏差:改判為無程式碼參照」即可,不需動程式。

**L3 — `CLAUDE.md` 新增的「there is no per-item write path」措辭過寬。**

- **證據/位置**:`CLAUDE.md:61`。但 `POST /admin/graph/{merge-nodes,delete-node,delete-edge}`
  (`routes_curation.py:66/76/84`)**仍是逐項、且不經兩道 gate 的 Neo4j 寫入**——
  Plan〈Out of Scope〉明確且合理地把它們排除(它們作用於**已核准**的圖譜,不是提案核准路徑)。
- **影響**:同段稍前的流程敘述有提到 `merge_nodes` / `delete_node`,讀者拼得回來;
  但這句話單獨被引用時會過度宣稱。對一份被當成權威上下文餵給 agent 的檔案,措辭精度值得在意。
- **修補方向**:把該句限定為「**提案進入圖譜**沒有單項路徑」,一詞之差。

### Suggestion

- **S1**:整份變更未 commit。`changes/` 亦為未追蹤。審查對象因此無法用 SHA 釘住,
  後續任何編輯與本報告引用的行號都可能對不上。建議在人類決定處置前先建立 commit
  (Plan 已註明 commit 需另行批准),讓審查、修補、複審有共同基準。
- **S2**:`CHANGE_REPORT.md` §2 用「(此處刻意不寫累計行數:`main..HEAD` 是會移動的目標)」
  說明為何不寫行數——這是上一輪審查的正確吸收。同樣的思路可以推廣到 H1:
  **文件同步的掃描面應該是一次全域 grep,而不是規劃時憑印象列出的檔案清單。**

## Requirement and Test Coverage Gaps

**移除兩個測試的等價覆蓋:核實成立。** 這是 `CHANGE_REPORT.md` L1 與 Plan R4 點名要審查者自行核對的項目:

- `test_review_groups.py:208 test_approve_group_writes_all_and_audits` —— 確實同時斷言
  **(a)** 核准前 Neo4j 查無(`_neo4j_node_status(...) is None`)、
  **(b)** 核准後為 `approved`、
  **(c)** 稽核列存在且 `action == "approve"`、`actor == "test_reviewer"`。
  **涵蓋被移除的 `test_approve_writes_to_neo4j_and_logs_change` 的全部斷言,且多一項。**
- `test_review_groups.py:225 test_reject_group_writes_nothing_and_audits` —— 確實斷言
  **(a)** Neo4j 未被寫入、**(b)** 稽核列 `action == "reject"`。
  **涵蓋被移除的 `test_reject_never_writes_to_neo4j_and_logs_change` 的斷言**,
  唯一差別是未斷言 `actor`(approve 那則有斷言)——**可忽略的落差**。

**一項細微的稽核粒度變化(非缺陷,僅記錄)**:舊測試查的是
`graph_change_logs.target_id = <節點 id>`,群組路徑記的是 `target_id = <group_id>`。
「哪個元素被核准」現在存在 `after_state.item_ids` / `after_state.nodes` 裡。
這是既有的群組設計(`changes/unified-two-gate-review` 已審過),不是本變更造成的迴歸,
但值得知道:**以節點 id 查稽核紀錄的舊習慣,在群組路徑下查不到東西。**

**未被任何測試涵蓋的情境**(Plan R3 / 報告 L2 已誠實揭露,此處確認確實無覆蓋):
其他機器上若存在 `group_id IS NULL` 的 `proposed` 舊列,移除後將永遠無法核准。
本機實測 0 筆。這是人類明確批准(D1/D2)的刻意結果,**非缺陷**,但也**沒有遷移或測試守著**。

## Compatibility, Security, and Scope Assessment

- **安全(改善)**:本變更**縮小**了攻擊面。被移除的 `approve_item` 是
  `docs/codereview_report/codereview_2026-07-08_b6def96.md` 記載的 Cypher label injection
  的觸發鏈路末端(`payload["type"]` → `load_neo4j._safe_type` 的 f-string 插補)。
  該漏洞當時以 `create_item` 加白名單修掉,如今**整條路徑消失**,防線從「靠驗證」變成「靠不存在」。
  這是正確的方向。
- **契約(破壞性縮減,已批准)**:三個 `POST` 消失。獨立複核消費端:
  全 repo grep(排除 `changes/`)僅命中 `README.md`(**文件,見 H1**)、`docs/graph_plan.md`、
  `docs/api_contract.md`、`docs/codereview_report/`、`docs/notes.md` 與新寫的註解/測試。
  **`frontend/`、`scripts/`、`app/eval/`、`ingestion/` 皆無呼叫**——與 Plan 的實測結論一致。
  無 openapi 快照或契約測試需同步。
- **範圍**:7 個修改檔案全部落在 Plan 批准路徑內,**未溢出**。
  群組路徑的 service 函式與其 36 個測試逐字未動(diff 可證),AC5 成立。
  **反向的範圍問題見 H1:應涵蓋而未涵蓋的檔案(README)落在批准路徑之外**——
  這不是實作者違規,是 Plan 的掃描面沒做完。
- **相容性/資料**:無 DB schema 變更、無 migration、無資料改寫。
  `curation_items` 的既有列(本機 19 + 1,皆有 group)不受影響。
  Rollback 為單純 `git revert`,無狀態需回捲——這點報告寫得準確。
- **授權/認證**:未觸及。移除的路由原本由 router 層的 `require_admin` 覆蓋;
  FastAPI 對不存在的路由在 auth 之前就回 404/405,不產生新的資訊洩露面。

## Unreviewed Areas and Residual Risk

- **未重跑任何測試或容器命令。** 本報告不獨立確認
  「241 passed / 1 pre-existing failure」與三項 lint 的結果;
  只確認了**測試數算式自洽**(`test_curation.py` 5 → 4)、
  失敗項與 memory 記載的既有 flake 相符,以及所有結論**皆可由 diff 與 grep 機械複核**。
  若要硬證據,應在乾淨 volume(`docker compose down -v`)的 CI runner 上重跑。
- **未做人眼前端驗證**(與報告 L3 相同的殘留風險)。依據僅為 grep。
- **未檢查其他機器/部署上是否存在無 group 的舊列**,亦無從檢查。
- **未審查群組路徑本身的正確性**——它不在本變更範圍內(逐字未改),
  但本變更把**所有**進入圖譜的流量收斂到它身上,
  因此 `approve_group` 的四道守衛從「主要路徑」變成「**唯一**路徑」。
  其品質由先前的 `changes/unified-two-gate-review` / `two-gate-review-p3` 審查背書,本次未複驗。
- **N7 未完成**:報告與 `docs/notes.md` 都明確寫了「後門已關 ≠ N7 完成」,
  residual 組逐項處置與 pattern 組「修正後核准」仍未做。**此揭露準確,無誤導。**

## Human Disposition Required

1. **H1(README / graph_plan)**:需決定是擴大批准路徑就地修掉,還是拆成後續變更。
   在修掉之前,**AC8 不應被記為通過**,`CHANGE_REPORT.md` §5 的「偏差:無」需更正。
2. **M1(守衛測試無鑑別力)**:需決定現在修(僅動已批准的 `test_curation.py`),
   還是接受並記為已知限制。**若接受,`CHANGE_REPORT.md` L4 需改寫**——
   目前它宣稱該測試「會擋住無意的回歸」,而對 approve/reject 兩條路徑並不會。
3. **L1–L3、S1–S2**:低成本、可批次處理,亦可全部接受。
4. **commit / push 授權**:Plan 註明需在審查後另行批准。

本次審查的核心結論:**後門確實關閉了,方向與執行都對;
問題出在「宣稱關閉」的證據品質(M1)與「宣稱文件同步」的掃描面(H1)。**

The reviewer does not approve, fix, merge, or release this change.
