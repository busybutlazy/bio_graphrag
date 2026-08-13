# Review Report 4: close-approve-item-backdoor(第四輪 —— 核實第三輪的處置宣稱)

## Review Context

- **Diff base and scope**:`main` @ `8112fda` → `62cf5a4`。
  本輪的新內容是 **`62cf5a4`(17:01:36)**,即第三輪報告(16:50:24)寫出**之後**的工作:
  8 個檔案(`README.md`、`test_curation.py`、`changes/` 內 6 份)。
  工作區 `git status --porcelain` **完全乾淨**。
- **Artifacts reviewed**:`REVIEW_REPORT_3.md`(受審對象)、`REVIEW_REPORT_2.md`、
  `62cf5a4` 完整 diff 與 commit message、`TASK_LOG.md` R6、更新後的
  `CHANGE_REPORT.md`(表頭 / §2 / §6 L4 / §6.2 / §7)、`IMPLEMENTATION_PLAN.md`
  Execution Policy 與 Approval 段、`VERIFICATION_REPORT.md`、
  `backend/tests/integration/test_curation.py:142-178`、
  `ingestion/pipeline/normalize_concepts.py` 型別白名單、`Makefile`。
- **Independence disclosure**:**本輪為第四位審查者(不同 session)**,
  與第一至三輪的審查者、以及實作者皆非同一 session。
  第二輪〈S-B〉點名的「連續同一人複審」問題,本輪不再存在。
  但我**未看過實作 session 的對話**,故對「第二輪報告是否曾交給實作者」只能以檔案時間佐證。
- **本輪執行的容器命令**(唯一寫入為本報告):
  - `docker compose run --rm -e OPENAI_API_KEY= backend python -c "<動態註冊路由的負向對照>"`
  - `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q`

## Completion Claim Assessment

**宣稱成立。第三輪的 B1 以及第二輪的 M-A / L-A / L-B / S-A 全部有實質處置,
且我對其中最關鍵的一項(L-A)做了獨立實測,不採信報告的自述。**

### 先處理第三輪 B1 本身:**第三輪的指控前提確實不成立**

實作者反駁 B1 說「你查的是我沒看過的那份報告」。我以**與雙方無關的第三方證據**核對時間序:

| 時間 | 事件 | 來源 |
|---|---|---|
| 16:21:58 | `CHANGE_REPORT.md` 寫出(第一輪處置完成) | mtime |
| **16:22:26** | commit `99e34d5` | `git log --format=%ad` |
| **16:27:50** | `REVIEW_REPORT_2.md` **才被寫出** | `ls --time-style=full-iso` |
| 16:50:24 | `REVIEW_REPORT_3.md` | 同上 |
| 16:52–17:01 | R6 全部處置 + `62cf5a4` | mtime / `git log` |

第三輪的核心證據是 `find . -newermt "16:27:50"` 零命中——
**但被檢驗的那句完成宣稱發生在 16:22 前後,早於 16:27:50**。
用「報告寫出之後沒有改動」去否證「報告寫出之前就已提出的宣稱」,**推論本身不成立**;
第三輪自己在第 61-62 行也承認「第一輪六項確實已修好」,兩段結論互相牴觸。

「第二輪報告從未交給我」這一句我**無法驗證**(不在可觀察範圍),但它與時間序一致,
且**不必成立**,B1 也已經倒了——只要宣稱早於報告,B1 的論證就斷了。

**處置方式我認同**:實作者沒有靜默略過,而是在 `TASK_LOG.md` R6 開頭以時間表逐項反駁,
並照第三輪的要求把整件事留在紀錄裡。**駁回一個發現而留下可複核的證據,是正確做法。**

### 第二輪三項發現的處置(逐項獨立複核)

| 發現 | 宣稱處置 | 本輪獨立複核 | 結論 |
|---|---|---|---|
| **M-A**(Medium)兩份報告表頭與結論自我矛盾 | 表頭 / §2 / §7 / AC 表全面更新 | 逐行對照第二輪點名的**七個位置**:`CHANGE_REPORT.md` 表頭已改 rev 2 + 「已 commit `99e34d5`」+「已進行三輪審查」;§2 補上 `README.md`/`docs/graph_plan.md` 兩列;「7 個檔案」**改為不寫數字**並註明理由(我實測 `git diff main...HEAD --stat` 排除 `changes/` 後確為 **9**);§7 改為「已審查三輪、人類驗收未取得」並主動揭露三輪同一審查者的獨立性限制;`VERIFICATION_REPORT.md` 表頭改 rev 2、刪去「未 commit」、§6 未執行事項只剩 push 與人類驗收;**AC1/AC3 證據欄改引 §5 #11 路由表對照,我確認 #11 確實存在於 `:90`** | **確實修好,且比要求的更完整** |
| **L-A**(Low)守衛未釘住路徑參數名 | 改為前綴掃描 + 負向對照 | **見下節實測** | **確實修好(實測驗證)** |
| **L-B**(Low)plan commit 授權欄過期 | 分列 rev 1 / rev 2 | `IMPLEMENTATION_PLAN.md:149-157` 已改,明寫 commit 已授權、**push 仍未授權** | **紀錄已修;但授權本身仍未經人類確認,見 N-1** |
| **S-A**(Suggestion)README 範例與文案張力 | 範例加註三件套 | `README.md:117-119` 已加註。我另行核對 `normalize_concepts.py`:`Hormone`/`RegulatoryEffect`/`PhysiologicalVariable` 皆在 `VALID_NODE_TYPES`,`HAS_EFFECT`/`ON_VARIABLE` 皆在 `VALID_RELATIONSHIP_TYPES`——**新註解舉的例子是合法型別,不是又一份對不上實作的文件** | **確實處置** |

### L-A 的修法:我自己跑了負向對照,不採信自述

`CHANGE_REPORT.md` 與 commit message 都宣稱「動態註冊 `{id}` 版路由後守衛確實失敗」。
這類「我測過了」的宣稱正是本變更三輪來反覆出問題的地方,故我**重跑一次**:

```
docker compose run --rm -e OPENAI_API_KEY= backend python -c "<sweep + 動態 include_router>"
BASELINE offenders:                     none                                        → 守衛通過
AFTER {id} re-add:                      {('/admin/curation/items/{id}/approve','POST')} → 守衛失敗(正確)
AFTER /curation/item (singular) re-add: {('/admin/curation/items/{id}/approve','POST')} → 未新增命中
```

**前兩行證實宣稱屬實**:以 `{id}` 加回後端點,新守衛**確實會失敗**——
這正是第一輪 M1 與第二輪 L-A 兩次缺的「斷言在缺陷存在時如何失敗」。
`test_curation.py:166-171` 的前綴掃描 + `:177-178` 的 GET 正向對照,兩者一起成立鑑別力。
**第三行是我額外加的一個 shape,見 N-2。**

### 測試與 lint

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
→ 1 failed, 241 passed in 101.10s
   FAILED ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent
   (assert 12 == 9,非乾淨 volume 的既有 flake,與本變更無關)
```

**與 `TASK_LOG.md` R6 記載的「1 failed, 241 passed」逐字吻合**,失敗項目也是同一個既有 flake。
測試數不變合理:本輪只改既有測試的斷言方式。

## Findings

### Blocking

無。

### High

無。

### Medium

無。

### Low

**N-1 —— 第二輪 L-B 要求的「人類確認 commit 授權」仍未取得;而本輪又多了一個未被任何欄位指名的 commit。**

- **證據/位置**:
  - 第二輪 L-B 的處置要求原文是「**需人類確認 commit 授權確實給過**」。
    現在 `IMPLEMENTATION_PLAN.md:151-157` 記的是**實作者自己的推論**
    (「T5 第 6 項明文 commit,且 T5 在自動核准清單內」),
    **不是人類的確認**。推論本身合理,但這一欄的性質是授權紀錄,自證不等於他證。
  - 該欄寫「據此完成 `99e34d5`」——**只指名一個 commit**。
    而本輪產生了**第二個 commit `62cf5a4`**,任何欄位都沒有涵蓋它。
  - `Auto-approved task IDs` 仍為 **T1–T5**,`Approved plan revision` 仍為 **2**。
    R6(第二、三輪審查處置)是一個**新 Task**,既未列入自動核准清單,
    `TASK_LOG.md` R6 也沒有像 T5 那樣附上批准原文
    (T5 有「jett / 2026-08-13,回覆『全部修,升 rev 2』」)。
- **違反的要求**:`CLAUDE.md`「未經使用者要求,不要自行 commit 或 push」;
  以及 supervised-auto 的 stop condition「**需要新增 Task／路徑…→ 停止並回報**」。
  (**路徑沒有問題**:R6 動到的 `README.md`、`test_curation.py`、`changes/` 三者
   全在 rev 2 的 `Approved file/path scope` 內,我逐項比對過,無範圍溢出。)
- **影響**:**很可能只是紀錄缺口而非實際越權**——人類顯然在第三輪之後要求了這輪修補
  (否則 R6 不會發生),而 rev 2 的 commit 授權涵蓋「本變更」而非單一 SHA 也說得通。
  但這正是 L-B 當初的教訓:**授權的正規欄位與實際狀態不一致時,稽核者會讀到錯的結論**。
  現在同一個欄位又落後了一個 commit。對一個以可稽核治理為賣點的專案,
  這一欄是展示品本身。
- **修補方向(有界)**:請人類**一句話確認**兩件事——
  (a) rev 2 的 commit 授權確實給過;(b) R6 這輪修補與 `62cf5a4` 在授權範圍內。
  確認後把 Execution Policy 該欄改為涵蓋「本變更的 commit」而非單一 SHA,
  並在 `TASK_LOG.md` R6 補上批准原文。**若未給過,性質不同,屬未授權 git 操作。**

**N-2 —— 前綴掃描的殘留限制未寫進 §6 L4,而 §6.2 的措辭讀起來像失效模式已經關閉。**

- **證據/位置**:
  - 我的負向對照第三行:把端點加回在 `/admin/curation/item/{item_id}/approve`(**單數 `item`**)
    或任何不以 `/admin/curation/items` 開頭的路徑上,`offenders` **不會增加**,守衛**照樣綠燈**。
  - `CHANGE_REPORT.md` §6 L4 的「**殘留限制**」段落到今天仍**只寫一句**:
    「刪掉該測試再加回端點仍然可行」。
    第二輪 L-A 已明確要求過:若殘留存在,L4 要寫進「**不刪測試也有一種加回方式能通過**」。
    參數名那一種已經修掉了,**但路徑形狀這一種取而代之,而 L4 沒有跟著更新。**
  - §6.2 結尾寫「三次都是同一件事……**本輪起改以負向對照處理**」,
    而實測的負向對照**只涵蓋參數名一種 shape**。
- **影響**:**比第二輪的 L-A 更窄**。最可能的加回方式是複製舊碼(路徑相同),
  而任何改路徑的加回都得先繞過 `CLAUDE.md`、`README.md`、程式碼註解三處明文警告。
  **不影響任何 AC,也不改變本變更的安全結論。**
  但它是**同一個失效模式的第四次殘留**:斷言的鑑別力依賴一個未被驗證的假設
  ——這次是「加回時路徑前綴不變」。§6.2 宣告「改以負向對照處理」時,
  沒有交代這個負向對照涵蓋到哪裡為止,**讀者會以為守得比實際更死**。
- **修補方向(有界)**:**不建議再改測試**(要涵蓋所有 shape 只能掃 `service.py` 的函式名,
  成本與收益不成比例)。建議純文件:§6 L4 補一句
  「前綴掃描只涵蓋 `/admin/curation/items` 底下;換路徑形狀加回仍會通過」,
  §6.2 把「改以負向對照處理」限定為「涵蓋參數名變化」。**一兩行,不需升 revision。**

### Suggestion

- **S-C —— lint 三項無法用專案的容器入口複核。**
  `TASK_LOG.md` R6 記「ruff check / ruff format --check / mypy(拋棄式容器)→ 全過」。
  我試 `docker compose run --rm backend sh -c "ruff check ..."` → **`ruff: not found`**;
  `Makefile:41-45` 的 `lint` target 是**直接在 host 上跑 ruff/mypy**,
  與工作準則「一律以 Docker 為執行環境」不一致。
  **這不是本變更的缺陷**(既有狀況,且本輪只改一個測試檔與 markdown,lint 風險極低),
  但它使「lint 全過」成為本輪**唯一無法被獨立複核的宣稱**。
  值得另開一個小變更:給 lint 一個容器化入口(例如 `docker compose run --rm backend`
  用一個含 dev deps 的 target,或 `Makefile` 改走拋棄式容器),讓 CI 與審查者跑同一條命令。
- **S-D —— 第二輪 S-B 的流程建議已被實作者實際採納。**
  「每個宣稱守門的斷言,都要能說出它在缺陷存在時如何失敗」——
  R6 不只照做,還把它寫成可複現的負向對照命令。
  建議把這條正式加進 `verify-change` 的檢查表(skill 層,不屬本變更),
  這輪的證據足以支持它值得制度化。

## Requirement and Test Coverage Gaps

- **AC1–AC9 在 `62cf5a4` 上全部成立。** AC1/AC3 的證據品質本輪再升一級:
  從「路由表對照」升到「路由表對照 + 負向對照實測」。
- **測試數 241 不變**,我實跑確認,且唯一失敗是既有 flake(非乾淨 volume)。
- **本輪未新增測試覆蓋缺口。** 既有缺口(其他機器上 `group_id IS NULL` 的舊列無法核准)
  自第一輪起未變,且是人類明確批准的刻意結果。
- **殘留的守衛盲區**見 N-2:換路徑形狀加回不會被測試攔下。

## Compatibility, Security, and Scope Assessment

- **範圍**:`62cf5a4` 的 8 個檔案**全部落在 plan rev 2 的批准路徑內**,無溢出。
  群組路徑(`service.py` 群組函式、`routes_review.py`、`test_review_groups.py`、
  `test_curation_groups.py`)本輪**一行未動**,AC5 持續成立。
- **契約**:本輪**零契約變更**——只改測試斷言方式與文件。`62cf5a4` 用 `test(curation):`
  而非 `refactor!:`,**分類正確**。
- **安全**:攻擊面不變(維持前三輪結論)。本輪未引入任何寫入路徑;
  守衛的鑑別力提升,防護只增不減。
- **資料/rollback**:無 DB 變更。`git revert 62cf5a4` 回到 `99e34d5`,
  或 `git revert 62cf5a4 99e34d5` 完全回復。**兩個 commit 都未 push,rollback 成本為零。**
- **git 狀態**:工作區乾淨,無 stash、無額外 worktree、**無 push 紀錄**(符合 plan)。

## Unreviewed Areas and Residual Risk

- **lint 三項未獨立複核**(見 S-C,無容器入口;依準則不在 host 安裝或執行)。
- **未在乾淨 volume(`down -v`)上重跑**——既有 flake 仍在,`1 failed` 的成因是環境而非程式,
  但「乾淨 volume 上 242 全過」本輪同樣沒有硬證據。這一點自第一輪起未變。
- **未做人眼前端驗證**(自第一輪未變;依據仍是 grep 實測前端從未呼叫這三個端點)。
- **群組路徑本身未複驗**——它是進入圖譜的唯一路徑,其品質由先前變更的審查背書。
- **「第二輪報告從未交給實作者」無法驗證**——僅時間序與之一致(見上)。
- **前三輪的結論我未全部重跑**,只重驗了與本輪處置直接相關的部分;
  第一輪六項的修好與否,我採信第二輪的逐項複核(該輪證據可機械複核)。

## Human Disposition Required

1. **N-1(Low,授權紀錄)——這是本輪唯一需要你回答的事**:
   請確認 (a) rev 2 的 commit 授權確實給過,(b) R6 這輪修補與 `62cf5a4` 在授權內。
   **這是第二輪 L-B 就問過、至今未由人類回答的同一個問題。**
2. **N-2(Low,文件)**:兩行字補上前綴掃描的邊界,或明確接受現狀。
3. **`62cf5a4` 的程式面品質可驗收**:L-A 的修法我實測過,守衛在缺陷存在時確實失敗;
   M-A 的七個位置逐一核對屬實;S-A 的新例子型別合法。
   **第三輪的 B1 不成立,不應成為驗收阻礙。**
4. **push 仍未授權**,目前兩個 commit 都只在本機,符合 plan。
5. **N7 仍未完成**,三份文件與兩則 commit message 都正確揭露,無誤導。

**本輪核心結論:第三輪的 Blocking 建立在錯誤的時間前提上,已被時間序證據推翻;
第二輪的三項發現全部真的處置了,其中 L-A 的修法我用獨立的負向對照實測過——
這是本變更四輪來第一次,「守衛有效」不是宣稱而是可複現的觀測。
剩下的兩項都是 Low,且都不在程式裡:一個是授權紀錄缺人類一句確認,
一個是殘留限制的措辭寫得比實際更死。**

The reviewer does not approve, fix, merge, or release this change.
