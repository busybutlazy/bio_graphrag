# Review Report 2: close-approve-item-backdoor(修補複審)

## Review Context

- **Diff base and scope**:`main` @ `8112fda` → `99e34d5`
  (`refactor(curation)!: remove the single-item write path that skipped both gates`)。
  工作區 `git status --porcelain` **完全乾淨**,14 個檔案(9 個程式/文件 + 5 個 `changes/` 產出物)。
  **第一輪的 S1 已解決**:本輪有 SHA 可釘,行號引用穩定。
- **Artifacts reviewed**:`REVIEW_REPORT.md`(第一輪)、plan rev 2、`TASK_LOG.md` T5、
  更新後的 `VERIFICATION_REPORT.md` §5、`CHANGE_REPORT.md` §5/§6.1、
  `99e34d5` 完整 diff、commit message、`routes_review.py`、`schemas/curation.py`、
  `main.py` 的 router 註冊、全域 grep。
- **Independence disclosure**:與第一輪為**同一位審查者**(獨立於實作 session)。
  **這是複審的固有弱點**:我在核對「我自己提的發現有沒有被修好」,
  對修法的認同存在確認偏誤。所有結論仍以可機械複核的證據呈現。
  未執行任何容器命令;**未重跑測試**(見〈Unreviewed Areas〉)。**唯一寫入為本報告。**

## Completion Claim Assessment

宣稱「五項發現全部處置完畢」。**逐項獨立複核:五項確實都真的修好了,無一是敷衍。**
但**修補過程本身產生了新的偏差**:兩份報告的表頭與結論段沒有跟著更新,
現在**自我矛盾**(說「審查未進行」的同時附著一節「審查處置」)。

| 第一輪發現 | 宣稱處置 | 本輪獨立複核 | 結論 |
|---|---|---|---|
| **H1**(High)README/graph_plan 仍教已移除端點 | README 改群組路徑;graph_plan 就地標注 | 我自己重跑全域 grep:README 已無任何命中;`graph_plan.md:366-369` 為刪除線+取代端點+更新說明;剩餘命中全部是正確描述「已移除」或歷史記錄(`changes/`、`docs/codereview_report/`) | **確實修好** |
| **M1**(Medium)守衛測試是同義反覆 | 改斷言路由表 + 正向對照 | `test_curation.py:157-172` 改為 `(path, "POST") not in registered`,**並以 `("/admin/curation/items","GET") in registered` 作正向對照**——這正是關鍵:它證明路徑字串格式(含 `/admin` prefix)假設正確,負向斷言不是因寫錯而恆真。router prefix 已獨立確認為 `/admin`(`routes_curation.py:32`) | **確實修好**(殘留見 L-A) |
| **L1** 稽核列殘留 | `finally` 內刪 `target_id=group_id` | `test_curation.py` 新增 `_delete_change_log`,在 `finally` 內以 `group_id` 精準刪除 | **確實修好** |
| **L2** AC 判準被改寫未標偏差 | 記入 `CHANGE_REPORT` §5 D-2 | §5 D-2 逐字承認「判準被改寫而未標為偏差」 | **確實修好** |
| **L3** `CLAUDE.md` 措辭過寬 | 限定為「no proposal reaches the graph one item at a time」 | `CLAUDE.md:61` 已改,**並加括號明確交代 `/admin/graph/{merge-nodes,delete-node,delete-edge}` 仍是逐項、刻意在 gate 之外、不是提案路徑** | **確實修好,且比我建議的更完整** |
| **S1** 未 commit | 人類批准後 commit | `99e34d5` 存在,commit message 完整記載 BREAKING CHANGE 與五項審查處置 | **確實修好**(授權紀錄見 L-B) |

**值得記錄的三件事**(審查的價值在於也要認可做對的部分):

1. **M1 的自我認定超出我提的程度。** `TASK_LOG.md` T5 不只承認「守衛是假的」,
   還自行以 `git show HEAD:backend/app/curation/service.py` 逐字確認被移除的 `approve_item`
   在 item 不存在時就回 404,並指出**「這與我上一個變更被審查抓到的 N-2 是同一種失效,
   換個地方又犯一次」**。把單點缺陷升級成失效模式的記錄,這是對的做法。
2. **範圍擴大依規範處理。** H1 需動 `README.md` / `docs/graph_plan.md`,在 rev 1 批准路徑之外,
   於是升 plan rev 2、重新記錄批准、新增 T5、並在 `CHANGE_REPORT` §5 D-3 標為偏差。
   **沒有靜默溢出。** 這正是 rev 1 的 stop condition 要求的行為。
3. **`VERIFICATION_REPORT.md` §5 主動作對自己不利的更正**——
   逐字寫下「第一輪驗證對 AC8 打了勾,而它當時不成立」,
   並主動指出 §3 那三行 curl「`-> 404` 的兩行不具鑑別力」。
   驗證報告承認自己的證據不成立,是這輪最有價值的產出。

**H1 的修補品質(不只是「有改」)**:README 新版把敘述從「New nodes/edges go through
human curation first」改寫為「提案的單位是**陳述**、要過 Schema gate 與專家兩道 gate」,
並新增一段解釋**為什麼沒有單項核准端點**。我逐欄核對了 curl 與實際 schema:
`proposed_nodes` / `proposed_edges` / `reason` 對得上 `CurationGroupCreate`
(`schemas/curation.py:29-39`),`{"reviewer","reason"}` 對得上 `ApproveRejectRequest` 與
`POST /admin/review/groups/{group_id}/approve`(`routes_review.py:34`)。
**README 的範例是可執行的**,不是又一份對不上實作的文件。

## Findings

### Blocking

無。

### High

無。

### Medium

**M-A — 兩份報告的表頭與結論段停在修補前,現在與自身內容矛盾。**

- **證據/位置**:
  - `CHANGE_REPORT.md:6`「**Plan revision**:1」——實際為 **rev 2**(§5 D-3 自己這樣寫)。
  - `CHANGE_REPORT.md:9`「**審查**:**未進行**。」——但 `§6.1` 標題就是「審查處置」,
    整節在逐項回應審查發現。**同一份文件同時說審查沒做過和審查做完了。**
  - `CHANGE_REPORT.md:130`(§7 未完成)「**獨立審查未進行**,人類驗收未取得。」——同上矛盾。
  - `CHANGE_REPORT.md:36` 的「文件同步」列仍只寫 `api_contract.md`、`CLAUDE.md`、`notes.md`,
    **漏了 T5 才加的 `README.md` 與 `docs/graph_plan.md`**——而那兩個正是 H1 的處置本體。
  - `CHANGE_REPORT.md:38`「程式與文件共 **7 個檔案**」——實際 **9 個**
    (`git diff main...HEAD --stat` 去掉 `changes/` 後為 9)。
    **諷刺的是下一行就是「此處刻意不寫累計行數:寫進文件就注定過期」**——
    同一個教訓在檔案數上又踩了一次。
  - `VERIFICATION_REPORT.md:3`「Plan revision: 1」;`:4`「**未 commit、未 push**」;
    `:103`「未執行的事項:**commit**、push、複審、人類驗收」——**commit 已於 `99e34d5` 完成**。
  - `VERIFICATION_REPORT.md:14/16` 的 AC1/AC3 證據欄仍寫「HTTP **404**(§3)」,
    而**同一份文件的 §5 已承認那個 404 不具鑑別力**。真正的證據(§5 表格 #11 路由表對照)
    沒有被拉進 AC 表。
- **違反的要求**:`CLAUDE.md` / 工作準則的「變更報告已產生,**無未揭露偏差**」與
  「相關文件已同步」;以及 Definition of Done 對報告準確性的要求。
- **影響**:`CHANGE_REPORT.md` 是**人類決定驗收與否時讀的那份文件**。
  它現在對「審查是否做過」給出兩個相反答案,對「plan 是第幾版」「動了幾個檔案」給出過期答案。
  一個只讀表頭與 §7 的人會得到「這個變更還沒被審查過」的結論——
  而這正好是驗收門檻的關鍵事實。對一個以**可稽核治理**為賣點的專案,
  變更報告自身的稽核性有瑕疵,傷的是論述本身。
  這不是新的實作缺陷,**危害僅限於文件誤導**,故不列 High。
- **修補方向(有界)**:更新 `CHANGE_REPORT.md` 表頭(rev 2、審查:已進行兩輪)、
  §2 表格補上 README/graph_plan 兩列、§2 的「7 個檔案」改為不寫數字或寫 9、
  §7 刪掉「獨立審查未進行」改為「複審已進行,人類驗收未取得」;
  `VERIFICATION_REPORT.md` 表頭改 rev 2、拿掉「未 commit」、§1 的 AC1/AC3 證據欄改引 #11 路由表對照、
  §6 未執行事項拿掉 commit。**全部落在 `changes/` 內,已在批准路徑中,無需再升 revision。**

### Low

**L-A — 新守衛以精確字串比對路由,路徑參數名未被正向對照釘住。**

- **證據/位置**:`backend/tests/integration/test_curation.py:160-166`
  ```python
  for path in ("/admin/curation/items",
               "/admin/curation/items/{item_id}/approve",
               "/admin/curation/items/{item_id}/reject"):
      assert (path, "POST") not in registered
  ```
  正向對照是 `("/admin/curation/items", "GET") in registered`(`:171`)——
  它釘住了 `/admin` prefix 與集合的建構方式,**但那條路徑沒有參數**,
  所以**沒有釘住 `{item_id}` 這個參數名**。若有人把端點加回來時寫成
  `@router.post("/curation/items/{id}/approve")`,`route.path` 會是
  `/admin/curation/items/{id}/approve`,負向斷言仍然成立 → **測試綠燈,後門回來了**。
- **影響**:比第一輪的 M1 **窄得多**——M1 是三條中兩條在任何情況下都失效,
  這裡只在「重新加回時換了參數名」才失效,而最可能的加回方式是複製舊碼(參數名相同)。
  但它是**同一個失效模式的殘留**:斷言的鑑別力依賴一個未被驗證的格式假設。
- **修補方向(有界)**:改以前綴比對取代精確字串,一行即可涵蓋所有形狀:
  ```python
  offenders = {(p, m) for (p, m) in registered
               if m == "POST" and p.startswith("/admin/curation/items")}
  assert not offenders, f"單項寫入路徑復活:{offenders}"
  ```
  仍只動 `test_curation.py`(批准路徑內)。**亦可接受並記為已知限制**,但若接受,
  `CHANGE_REPORT.md` §6 L4 的「殘留限制」段落應把這一條寫進去——
  目前它只寫了「刪掉測試再加回端點仍可行」,沒寫「不刪測試也有一種加回方式能通過」。

**L-B — commit 已發生,但 plan 的 Execution Policy 仍記載「commit 未授權」。**

- **證據/位置**:`IMPLEMENTATION_PLAN.md:149`
  「**Commit/push permission**: **No unless separately approved after review.**」——
  **rev 2 未更新此欄**。授權的線索散在別處:T5 實作項第 6 點「本變更在人類批准後 commit」、
  rev 2 批准欄「jett / 2026-08-13(回覆「全部修,升 rev 2」)」、
  auto-approved tasks 含 **T5**。commit `99e34d5` 確實存在。
- **影響**:授權**很可能真的取得了**(T5 含 commit,而 T5 在 rev 2 的自動核准清單內),
  所以我不把它列為未授權操作。問題在於**記錄方式**:
  Execution Policy 是這份 plan 記載 git 權限的**正規欄位**,它現在說「否」,
  而實際狀態是「已 commit」。任何第三方稽核者會先看那一欄並得到錯誤結論。
  `CLAUDE.md` 明文要求「未經使用者要求,不要自行 commit 或 push」,
  因此這一欄的準確性不是形式問題。
- **修補方向**:把 `IMPLEMENTATION_PLAN.md:149` 更新為
  「rev 2:commit 已授權(jett / 2026-08-13,S1),**push 仍未授權**」,
  並在〈Approval evidence〉補一句 rev 2 的批准原文。
  **需人類確認 commit 授權確實給過**——若沒給過,這就不是文件問題,而是一次未授權的 git 操作。

### Suggestion

- **S-A**:README 新版寫「the unit of proposal is a **statement** … never a loose element」,
  而緊接的範例是**一個沒有邊的單節點群組**。我已確認這在實作上**合法**
  (`test_proposed_statement_reaches_the_graph_only_after_approval` 正是這個形狀,201 → approve 200),
  所以範例不會壞。但文案與範例的張力仍在:讀者會問「這不就是 loose element 嗎」。
  可在範例註解補一句「最小示例;真實提案通常是 Hormone→RegulatoryEffect→PhysiologicalVariable 三件套」。
  **純文案,不影響正確性。**
- **S-B**:本輪由**第一輪的同一人**複審(見〈Independence disclosure〉)。
  M1 這類「守衛看似存在、實則無鑑別力」的缺陷連續兩個變更出現
  (T5 自己點名與上個變更的 N-2 同型),值得考慮:
  在 `verify-change` 的檢查表加一條**「每個宣稱守門的斷言,都要能說出它在缺陷存在時如何失敗」**,
  把這件事變成流程,而不是靠審查者每次抓。這是 skill 層的改動,不屬本變更。

## Requirement and Test Coverage Gaps

- **AC1–AC9 現在全部成立。** AC8 由 T5 補完(README + graph_plan),我已用獨立的全域 grep 確認;
  AC1/AC3 的證據品質由路由表對照取代不具鑑別力的 404。
- **測試數 241 不變**是合理的:T5 只改既有測試的斷言方式與清理,未增減測試。
- **第一輪確認過、本輪未重驗**:移除的兩個測試在 `test_review_groups.py:208/:225` 確有等價覆蓋。
  該檔本輪仍**一行未改**(diff 可證),結論延用。
- **仍無測試涵蓋**(自第一輪起未變,且為人類明確批准的刻意結果):
  其他機器上 `group_id IS NULL` 的 `proposed` 舊列移除後無法核准。

## Compatibility, Security, and Scope Assessment

- **範圍**:9 個程式/文件檔案全部落在 **plan rev 2** 的批准路徑內。
  群組路徑(`service.py` 的群組函式、`routes_review.py`、`test_review_groups.py`、
  `test_curation_groups.py`)**逐字未動**,AC5 持續成立。
- **契約**:與第一輪相同的破壞性縮減,已批准;commit message 以
  `refactor(curation)!:` 與 `BREAKING CHANGE:` 段落正確標示,並寫出替代端點。
  **這是本變更對外溝通做得最好的一環。**
- **安全**:維持第一輪結論——攻擊面縮小,
  被移除的 `approve_item` 是既往 Cypher label injection 的觸發鏈路末端。T5 未引入新的寫入路徑。
- **資料/rollback**:無 DB 變更;`git revert 99e34d5` 即完全回復。

## Unreviewed Areas and Residual Risk

- **本輪未重跑任何測試或容器命令。** 不獨立確認「1 failed, 241 passed」與三項 lint。
  所依據的是:T5 的改動可**靜態複核**(路由表斷言的正確性由 router prefix `/admin`
  與正向對照共同確立),且 `VERIFICATION_REPORT.md` §5 附了 #9–#12 的重跑輸出。
  **要硬證據仍需乾淨 volume(`down -v`)的 CI runner。**
- **複審獨立性受限**(同一審查者,見上)。若這個變更要當作履歷展示的治理範例,
  找第二位審查者或人類複看 M1 的修法值得考慮。
- **未做人眼前端驗證**(自第一輪未變)。
- **群組路徑本身未複驗**——它現在是進入圖譜的唯一路徑,
  其品質由先前變更的審查背書,本輪未重看。
- **`docs/codereview_report/` 內對舊端點的描述刻意未動**(歷史稽核記錄),我認同此處置。

## Human Disposition Required

1. **M-A(Medium,報告自我矛盾)**:建議修完再驗收。全部在 `changes/` 內,
   無需升 revision,成本很低,但它影響的是驗收者讀到的事實。
2. **L-A(守衛的參數名殘留)**:修(一行改前綴比對)或接受並補進 `CHANGE_REPORT` §6 L4。
3. **L-B(commit 授權紀錄)**:**請人類確認 commit 授權確實給過**;
   給過則更新 `IMPLEMENTATION_PLAN.md:149`,未給過則屬未授權 git 操作,性質不同。
4. **push 仍未授權**——目前只有本機 commit,無 push 紀錄,符合 plan。
5. **N7 仍未完成**,兩份文件與 commit message 都正確揭露了這點,無誤導。

**本輪核心結論:五項發現全部真的修好了,H1 與 M1 的修法都超出最低要求
(M1 附了正向對照,L3 比我建議的更完整)。
剩下的問題不在程式,而在**報告沒有跟著修補一起更新**——
變更報告現在同時聲稱審查未進行與審查已處置。**

The reviewer does not approve, fix, merge, or release this change.
