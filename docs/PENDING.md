# Pending

受控的延後問題清單。每一項是開發中發現有效、但不屬於當時 Change scope 的問題。**Pending capture
不授權實作**,也不應偷偷擴張目前進行中的 Change。欄位定義見 `docs/agent-guideline.md` §1。

沿用原 `docs/notes.md` 的 N 編號,以維持既有 Change 記錄（例如 `changes/containerize-lint/CHANGE.md`
的 N13、N14 引用)的可追溯性。已解決的項目不留在本檔——其結果收斂進對應 Change 的 `CHANGE.md`。

────────────────────────────────────────

## N2 — 為 `endocrine_demo_v1` 寫 extraction profile

限定型別、講清楚 `HAS_EFFECT` / `ON_VARIABLE` 方向、附正確範例。

- **狀態**: **N1 前置已解除,內容是否足夠待人類判斷**。原 blocking trigger（N1 完成之後）已滿足——
  `changes/structured-outputs-extraction`（PR #20,`51a2056`／`521197c`／`f9e1929`)已合併進
  `main`:`build_strict_schema()`、`salvage.py`、`runner.ExtractionAttempt` 均在現行程式碼中,
  真實抽取由 `failed_chunks 2/4` 降為 `0/4`。原 N1 項目已從本檔移除（結果見該 change 的
  `CHANGE_REPORT.md`,未收斂成 `CHANGE.md`)。
- **新發現**: `prompts/profiles/endocrine_v1.profile.md` 已存在（最後修改 2026-07-21,早於 N1
  合併),內容已涵蓋「限定 node/relationship type、RegulatoryEffect 方向與 id 慣例、
  HAS_EFFECT/ON_VARIABLE 相關 few-shot 範例」,表面上與本項訴求高度重疊。**本次 triage 未判斷
  該檔是否已足夠**——是否需要針對 N1 之後的 strict-schema 輸出重新驗證/修訂,屬內容判斷,
  留待人類或下一輪 grill 決定,不由 triage 逕行認定完成。
- **來源**: 抽取品質檢視「發現二」
- **Evidence**: 未附具體引用（承接自舊記錄);`prompts/profiles/endocrine_v1.profile.md` 現存內容見上
- **延後理由（原始）**: 需要 N1 先穩住輸出形式,才驗得出內容改善——此前置條件現已成立
- **可能後果**: 若現有 profile 內容不足,抽取內容品質（型別誤用、關係方向錯誤）持續不受 profile 約束;
  若已足夠但未經確認,則本項目在 Pending 中空占位
- **Blocking trigger**: 已解除（N1 完成)。下一個動作是人類判斷 `endocrine_v1.profile.md` 是否已滿足
  本項訴求,而非預設要另開一次花 token 的驗證
- **Owner**: 未指定
- **範圍**: 待定——視人類判斷結果,可能是「無需新 change（現有檔案已足夠,關閉本項)」或「小 change
  （用現有真實章節跑一次驗證/修訂 profile)」
- **關聯操作（2026-08-14)**: 公開 demo vendor key（原 N12,已執行)的 quota 已人為調成 0
  （`vendor_usage.used=1748 > quota=0`,呈現 `quota_exceeded`),原因就是本項未確認完——
  在確認 `endocrine_v1.profile.md` 是否足夠、抽取品質站得住腳之前,先不讓讀者實際試用。
  **本項確認完成(或決定不需再動)後,記得把 quota 調回 5,000,000**
  （`docker compose run --rm backend python scripts/manage_vendors.py update --code demo --quota 5000000`)。

────────────────────────────────────────

## N3 — 專家 lens 敘述品質

`PART_OF` 等簡單關係講成人話、重寫「請就內容本身審查」的措辭。

- **來源**: 先前一輪 grill 已選 A（延後)
- **Evidence**: 殘餘組（非 pattern anchor 的節點/邊）在每章抽取結果中都會出現
- **延後理由**: 與抽取邏輯無關,純敘述層問題
- **可能後果**: 專家審閱介面的可讀性持續偏低,尤其殘餘組
- **Blocking trigger**: 未明確記載（獨立事項,無外部依賴）
- **Owner**: 未指定
- **範圍**: 新 change（需一輪 grill 定義「哪些關係怎麼講」）

────────────────────────────────────────

## N4 — schema-gap backlog 生命週期（DF1）

accept／reject／復原、engineer override、孤兒 JSON 去留。

- **來源**: `changes/phase-p5-run-2026-08-11/DECISION_READINESS_SUMMARY.md` §Intentionally Deferred Decisions（grill 已定案延後）
- **Evidence**: `changes/group-review-gap-outcome/CHANGE_REPORT.md` 已交付「record-as-gap 寫入路徑」,但其文件明記 backlog **檢視畫面缺席**——只有寫入,沒有管理介面
- **延後理由**: 抽取分組（P5 第一交付項）的 implementation plan 可在不假設任何 backlog 答案下完整寫出
- **可能後果**: 被記為 `schema_gap` 的群組目前只能寫入,無 accept/reject/復原操作,也無 engineer override
- **Blocking trigger**: 對真實章節（非 demo 來源)記錄 gap 時,或宣告 Roadmap P5 完成時
- **Owner**: owner
- **範圍**: 新 phase（Roadmap P5 第二交付項）

────────────────────────────────────────

## N5 — gold 改打真實抽取輸出（DF2）

- **狀態**: N1 半已完成（見 N2 狀態行,PR #20 已合併),仍卡在 N2（profile 內容是否足夠未定案）
- **來源**: `changes/phase-p5-run-2026-08-11/DECISION_READINESS_SUMMARY.md` §Intentionally Deferred Decisions
- **Evidence**: 現有 gold（6 tests,全綠）仍是有效的 renderer 回歸網,未依賴真實抽取輸出
- **延後理由**: 需要 N1 + N2 讓抽取品質穩定後,以真實輸出作為 golden 基準才有意義;N1 已滿足,N2 未定案
- **可能後果**: golden regression 持續只驗證 renderer,不驗證真實抽取品質
- **Blocking trigger**: 宣告 Roadmap P5 完成時,或要以真實抽取輸出作為 golden 基準時
- **Owner**: owner
- **範圍**: P5 收尾

────────────────────────────────────────

## N6 — 稽核 actor 由 admin key 決定（S1）

- **來源**: 上一輪審查定為獨立 Phase
- **Evidence**: 未附具體引用（承接自舊記錄)
- **延後理由**: 含契約變更與 `/admin` 上線姿態,範圍需獨立定義
- **可能後果**: `graph_change_logs` 的 actor 欄位語意（是否可信地對應到發起請求的 admin key）未定案前,稽核紀錄的可信度有已知缺口
- **Blocking trigger**: 未明確記載
- **Owner**: 未指定
- **範圍**: 新 phase

────────────────────────────────────────

## N7 — 群組審閱的部分處置（residual 逐項 / pattern 修正後核准）

- **狀態**: **部分完成**。旁支問題（`approve_item` 後門）已關閉,原始問題（部分處置）仍未做。
- **來源**: 2026-08-12 發現
- **Evidence**: `service.py` 目前只有 create/approve/reject,沒有 update,故 pattern 組（本身是一條陳述）
  今天只能整組退回重提,無法「改了再核准」;residual 組（lens 渲染為「不屬於任何已知的調控模式」）
  逐項處置沒有原子性要守,整包丟棄純屬浪費
- **已完成部分**: `approve_item`（無 group 意識,繞過 Schema gate、反向翻譯、deprecated 與懸空邊防線）
  已於 `changes/close-approve-item-backdoor`（2026-08-13）連同 `create_item` 的無 `group_id` 缺口一併移除;
  進入圖譜現在只有群組端點一個入口
- **仍未做**: residual 組逐項處置、pattern 組「修正後核准」——`service.py` 仍無 update 能力
- **延後理由**: 需要一輪 grill 定義部分處置的邊界
- **可能後果**: 專家審閱 pattern 組時,若只有部分內容需要修正,仍只能整組退回重提,無法局部修正後核准
- **Blocking trigger**: 未明確記載
- **Owner**: 未指定
- **範圍**: 新 change（需一輪 grill 定義部分處置的邊界）

────────────────────────────────────────

## N8 — 長時間 ingest 的請求形態

`POST /admin/ingest/run` 同步阻塞,四個 chunk 約 4 分鐘,超過 nginx 預設代理逾時。

- **狀態**: **部分完成**。方案 (c) 已完成,方案 (a)(b) 仍未做。
- **來源**: 2026-08-12 實際踩到
- **Evidence**: nginx 回 504 但後端仍跑完,操作者（或 agent）誤判為失敗而重試,造成第二次抽取同時在跑,
  重複花費約 15–25k tokens
- **已完成部分**: 方案 (c)——`changes/ingest-concurrency-guard`（2026-08-13）。同來源已有進行中的抽取
  job 時,`POST /admin/ingest/run` 在花掉任何 token 之前回 `409 ingest_already_running`,訊息含擋住的
  job_id 與「不要重試」。實作為 `ingestion_jobs` 上的部分唯一索引,孤兒列 2 小時後自動失效
- **仍未做**: 方案 (a)（調高 nginx 逾時,治標)與方案 (b)（改為非同步:回 job_id + 輪詢
  `/admin/ingest/jobs/{id}`,治本但是契約變更)。504 本身還在,操作者仍會看到逾時,只是重試不再扣款
- **延後理由**: (b) 是契約變更,需要動 `docs/api_contract.md` 與前端匯入頁,留待獨立變更
- **可能後果**: 操作者持續會看到 504 逾時（即使重試已無害),介面觀感未修
- **Blocking trigger**: 未明確記載
- **Owner**: 未指定
- **範圍**: 新 change（含契約決策)

────────────────────────────────────────

## N9 — ingest 併發防護的審查殘留項

- **來源**: `changes/ingest-concurrency-guard` REVIEW_REPORT,2026-08-13。該次審查無 Blocking/High;
  M-1、S-1 已於同分支修掉,以下為刻意延後項目
- **Evidence / 可能後果**（逐項,皆屬「測試全綠卻靜默失效」或「訊息誤導操作者」類型）:
  - **L-1** 防護鍵是 `source_path`,破壞性寫入鍵是 `doc_id`。兩個不同來源檔可有相同 `doc_id`
    （front-matter 手寫撞名,或 sample/private 同 stem),此時防護放行,後到的
    `delete_chunks_for_doc(doc_id)` 可能清掉先到者剛寫好的 chunks（PG 與 Qdrant 皆然)。
    是資料一致性缺口,非重複扣款。最小處置:`docs/api_contract.md` 補一句「前提是兩來源
    `doc_id` 不同」;根治要把防護鍵改成 `doc_id` 或加唯一性檢查
  - **L-2** claim 的 INSERT 失敗與查詢之間有毫秒窗口。擋住的 job 若剛好在此期間結束,訊息退化成
    `job_id=None、開始於 未知時間`,卻仍叫人不要重試——而此刻重試會成功。處置:
    `blocking is None` 時重試一次 claim
  - **L-3** HTTP 測試在真實 demo 章節路徑上留 `running` 列,只靠 `finally` 清。pytest 被硬殺時
    開發機的 demo 章節會被鎖 2 小時,症狀與真實事故無法區分。處置:改用不對應真實檔案的 source_path
  - **S-2** `_second_connection()` 逐字複製了 `conftest.py::pg_conn` 的連線參數。conftest 若改來源,
    這裡不會跟著改,「兩條連線指向同一個 DB」會靜默變假而測試仍過。處置:把連線工廠抽到 conftest 共用
  - **S-3** `ensure_schema` 每次啟動與每次 `/admin/ingest/run` 都跑一次全表 UPDATE。目前約 100 列
    可忽略;成長後再收斂為「索引不存在時才跑」。**現階段 YAGNI,不要動**
  - **既有觀察**（先於本變更,未實測,兩種結果皆可能）: `runner.py` 的 `except Exception` 抓不到
    `CancelledError`。優雅取消時若 `finally` 跑完,會用初始值 `status="success"` 收尾,把被中斷的
    job 記成成功（稽核紀錄說謊,但鎖有釋放);若 `finally` 內的 `await finish_ingestion_job(...)`
    本身也被取消打斷,該列留在 `running`,**鎖被洩漏 2 小時**。不要假設取消時機的方向是安全的
- **延後理由**: 皆不緊急,值得在下次動到 ingest 時一併處理
- **Blocking trigger**: 下次修改 `ingestion/extract/runner.py` 或 ingest 併發防護相關程式碼時
- **Owner**: 未指定
- **範圍**: 後續 change（可拆,皆為小範圍)

────────────────────────────────────────

## N11 — `verify-change` 檢查表新增「負向對照」規則（skill 層)

- **來源**: 第四輪審查 S-D
- **Evidence**: 同一失效模式在兩個變更裡出現四次——`ingest-concurrency-guard` N-2（斷言只命中訊息的
  一半)、`close-approve-item-backdoor` M1（斷言依賴狀態碼,而被移除的 handler 也回同一個碼)、
  L-A（依賴路徑參數名)、N-2（依賴路徑前綴)。四次都是:宣稱守門的斷言,鑑別力靠一個沒被驗證的格式假設,
  於是測試在缺陷存在時照樣綠燈
- **延後理由**: 屬 skill 層改動（`canonical-configs/`),不屬任何單一專案變更
- **可能後果**: 同一失效模式在未來變更中持續重演,只能靠審查者每次人工抓
- **建議做法**: `verify-change` 增列一條——凡宣稱「守住某個回歸」的斷言,驗證報告必須附一個負向對照
  （實際製造出該缺陷,證明斷言會失敗),或明寫涵蓋範圍到哪為止
- **附帶項（第五輪審查 S-E)**: 「人類交來審查報告」不等於「授權繼續執行」,但實作端會這樣讀
  （`close-approve-item-backdoor` R6/R7 即如此發生)。建議在 `review-change` template 補一句對實作端
  說的話:本報告不構成執行授權;處置前需取得人類對「新增 Task／範圍」的批准
- **Blocking trigger**: 未明確記載
- **Owner**: 未指定
- **範圍**: skill 層 change（`canonical-configs/agent-memory/`,非本專案 change)

────────────────────────────────────────

## N13 — 強化 mypy 訊號:讓 type-check 看得見 runtime 套件的真實型別

- **來源**: `changes/containerize-lint` D1 刻意延後（2026-08-14)
- **Evidence**: 現行 lint 映像只裝 dev tooling,與原本 CI 等價,但 fastapi / pydantic / asyncpg
  全走 `ignore_missing_imports`,型別訊號偏弱
- **延後理由**: 若把 lint stage 疊在 backend runtime image 上,mypy 會第一次看到真實型別,預期一次
  冒出可觀的既有錯誤——那是獨立的「修型別」工作,不該混進換執行方式的變更裡
- **可能後果**: mypy 持續無法捕捉 fastapi / pydantic / asyncpg 相關的真實型別錯誤
- **Blocking trigger**: 未明確記載
- **Owner**: 未指定
- **範圍**: 新 change（動 `backend/Dockerfile` 一行 + 後續修型別,規模未知)
