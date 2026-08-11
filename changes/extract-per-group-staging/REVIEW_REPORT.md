# Review Report: extract-per-group-staging

## Review Context

- **Diff base and scope:** `0a3e5be..f4af033`（分支 `feat/extract-per-group-staging`,三個 commit:
  `12887d2` 切分器 → `250f9c3` 巢狀 anchor + 端點 guard → `f4af033` staging)。20 個檔案,
  +1953 / −67。
- **Artifacts reviewed:** `IMPLEMENTATION_PLAN.md`（revision 3)、`TASK_LOG.md`、
  `VERIFICATION_REPORT.md`、`CHANGE_REPORT.md`、完整 diff、
  `group_statements.py`、`load_postgres.stage_extraction_output`、`runner.ingest_document`、
  `curation/service.py::{create_group, approve_group, list_groups}`、
  `graph/engineer_gate.py`、`graph/back_translation.py`、四份測試檔、`docs/api_contract.md`、前端 diff。
- **Independence disclosure:** 本次審查在**獨立的 session** 進行,未參與規劃或實作,未讀取實作
  session 的對話脈絡。與實作者共用同一位人類 owner——最終處置仍需人類判斷。
- **執行的驗證:** 僅在既有 `backend` 容器內以 `docker compose exec` 跑**純計算探測**(不寫任何
  資料庫、不建立容器、不改檔案)。未重跑測試套件,未 push,未執行 CI。

## Completion Claim Assessment

變更報告宣稱「接通了本專案敘事的主線」。**部分成立。** 抽取輸出確實開始帶 `group_id` 並出現在
群組審閱佇列——這一點有端到端證據,可信。

但宣稱背後的核心設計前提**未成立於一般情況**:`group_statements.py` 的模組 docstring 明言此模組
存在的目的是防止「一個群組裝著兩個陳述時,`render_understanding` 只描述它找到的**第一個** pattern,
另一個就搭便車無聲進入圖譜」。實測顯示**殘餘組(residual)仍然正是這種桶子**,而且它額外帶著
懸空端點,會被本次新增的第六道防線擋下(見 H1、H2)。三個新增的驗收標準(AC1/AC2/AC3)的測試
都繞開了這個形態:切分器的六個單元測試裡,沒有一個讓殘餘邊指向被 anchor 組收走的節點。

`VERIFICATION_REPORT.md` 的「Owed / Not Run」段落自陳誠實(瀏覽器確認、CI 未跑、未重跑真實抽取),
沒有發現誇大或掩飾的紀錄。反向驗證(漂移守衛、端點 guard)是實作品質的加分項。

## Findings

### Blocking

**B1 — 殘餘組會攜帶懸空端點,被新的第六道防線永久擋死(直接回答 reviewer 提問 1:會誤擋)**

- **證據/位置:** `ingestion/pipeline/group_statements.py:103`
  (`residual_nodes = [n for n in nodes if n["id"] not in claimed_nodes]`)配合
  `:77-79`(`residual_edges` 只排除**兩端都非 anchor**的邊)。
  `backend/app/curation/service.py:519-535`(新 guard)。
- **實測(容器內純計算探測,一個完全普通的血糖章節 chunk):**

  ```text
  GROUP group:llm:c1:regulatory_effect:lower_bg
    nodes: [hormone:insulin, physiological_variable:bg, regulatory_effect:lower_bg]
    edges: [e:1 HAS_EFFECT, e:2 ON_VARIABLE, e:3 DECREASES]      dangling: []
  GROUP group:llm:c1:residual
    nodes: [structure:pancreas]
    edges: [e:4 SECRETES pancreas→insulin, e:5 REGULATES_SECRETION_OF bg→insulin]
    dangling: ['hormone:insulin', 'physiological_variable:bg']    gate: pass
  ```

  `insulin` 與 `bg` 被 RE 組 `claimed_nodes` 收走,殘餘組只剩指向它們的邊。Schema gate **通過**
  (JSON Schema 無法做參照完整性;`_pattern_check` 在無 anchor 時回 `None`),所以流程會走到新的
  第六道防線 → **409**。
- **違反的要求 / 風險:** 這不是壞資料,是切分器對**任何**含「腺體分泌激素」句子的 chunk 的正常輸出
  ——而分泌正是本領域最常見的敘述。
- **影響:**
  1. 殘餘組必須在它從未被告知的「擁有者」RE 組**之後**才能核准。`api_contract.md` 與
     `IMPLEMENTATION_PLAN.md` 的 R6 只記載了「交互作用 → 效果」這一種順序依賴,**沒有記載這一種**。
  2. 更嚴重:若該 RE 組被**駁回**——而 `CHANGE_REPORT.md` 自己記載真實抽取「5 組中 4 組
     `fail_pattern`」——`insulin` 永遠不會成為 approved 節點,**殘餘組就永久無法核准**,且錯誤訊息
     「approve the group that proposes them first」指向一個已經不在佇列裡的群組,審閱者無從補救。
     這是一個沒有出口的死結,只能從資料庫手動刪列。
- **有界的修正方向(擇一,不在此決定):**
  (a) 切分器把「被 anchor 收走、但仍被殘餘邊引用的節點」複製回殘餘組——與 AC1「共用變數同時出現在
      兩組」已採用的規則一致,成本最低;
  (b) 或殘餘邊比照 anchor 邊,連同其端點一起納入殘餘組;
  (c) 或在 staging 端先偵測跨組懸空並拒絕,不要留到核准時才 409。
  無論擇哪一項,都應補一個「殘餘邊指向被收走節點」的切分器單元測試,並在 `api_contract.md` 補記
  這條順序依賴。

### High

**H2 — 殘餘組仍是多陳述桶子,`render_understanding` 只描述其中第一個(本模組宣稱要防止的失效)**

- **證據/位置:** `group_statements.py:1-17`(docstring 宣稱)vs
  `backend/app/graph/back_translation.py:74-120`(P2 → P4 → P1/P3 依序 return,先命中先返回)。
- **實測:** 在上例再加一個 `misconception:hormone_is_enzyme ─COMMONLY_CONFUSED_WITH→ insulin`:

  ```text
  group:llm:c1:residual | gate: pass
     sentence: 當bg改變時,胰臟會分泌insulin。          ← P2 secretion_trigger
     members not described by that sentence: ['misconception:hormone_is_enzyme']
  ```

  殘餘組拿到的**不是** `CHANGE_REPORT.md`「Known consequences」所述的 P0 plain summary,而是一個
  **P2 pattern 句**;誤解節點完全沒被那句話描述,若該組獲准就會無聲進入圖譜。
- **根因:** `PATTERN_ANCHOR_TYPES = {RegulatoryEffect, Interaction}` 只對齊 `engineer_gate`,
  沒有對齊 `back_translation`。後者有**四**個 pattern:P2 `secretion_trigger` 的形狀是
  `Var ─REGULATES_SECRETION_OF→ Hormone` + `Structure ─SECRETES→ Hormone`,**沒有 anchor 型別**,
  所以一個完整的分泌陳述永遠不會自成一組,一律落進殘餘桶。
- **影響:** 本變更的核心主張(一組 = 一個陳述)對四個 pattern 中的一個不成立;而該 pattern 又恰好
  是最常出現的形態之一。新增的漂移守衛
  (`test_pattern_anchor_types_cover_every_type_the_gate_special_cases`)只釘住
  splitter ↔ `engineer_gate`,**沒有**釘住 splitter ↔ `back_translation`,所以這個落差不會被測試發現。
- **有界的修正方向:** 決定 P2 是否要成為第三種切分單位(若要,anchor 概念需從「節點型別」擴為
  「邊形狀」);短期至少補一個守衛,斷言 `render_understanding` 對殘餘組**只會**回 `is_gap` /
  plain summary,一旦回了 pattern 句就讓測試失敗。此項牽涉 `back_translation`,依 Plan 第 165 行
  屬於 stop condition,應由人類決定納入本 change 或另開。

### Medium

**M1 — `_edge_owner` 的「source wins」與 gate 的一致性是巧合,不是結構性的(直接回答 reviewer 提問 2)**

- **證據/位置:** `group_statements.py:36-52` docstring 宣稱「in both cases ownership lands where the
  pattern rule looks」;`engineer_gate.py:44-56` 中 `RegulatoryEffect` 的檢查是
  `inc(nid, "HAS_EFFECT")`——一條**入邊**。
- **論證:** 對入邊規則而言,「source wins」把邊判給 source;只有當 source **不是 anchor**
  (現況 `HAS_EFFECT` 的 source 是 `Hormone`)時,邊才會留在做檢查的那一端。真正與 gate 對齊的規則是
  「**由 pattern 規則會去看這條邊的那一端擁有它**」——對 out-edge 是 source,對 in-edge 是 target。
  兩者今天同解,是因為唯一的 anchor-anchor 邊(`USES_EFFECT`)恰好是 out-edge 檢查。
- **影響(可觸發):** 若 LLM 產出 `RegulatoryEffect ─HAS_EFFECT→ RegulatoryEffect`,source wins 會把邊
  判給來源 RE,**目標 RE 就失去它必需的 HAS_EFFECT 入邊 → 該組永久 `fail_pattern`**。這不是理論
  形態:`CHANGE_REPORT.md` 自己記載真實抽取已經把 `HAS_EFFECT` 用成
  `RegulatoryEffect → PhysiologicalVariable`,亦即模型確實會拿 anchor 當 `HAS_EFFECT` 的 source。
  後果是降級(reviewer 駁回)而非資料損毀,故非 Blocking。
- **有界的修正方向:** 要嘛把規則改成依 gate 的 in/out 方向決定歸屬,要嘛把 docstring 的通則主張
  降格為「僅對現有型別集合成立」並加註前提(source 為非 anchor),並補一個
  anchor─`HAS_EFFECT`→anchor 的單元測試釘住實際行為。

**M2 — 依設計強制的核准順序,交互作用組給專家看到的句子會退化**

- **證據:** `back_translation.py:34-42`,`effect_to_hormone` **只**由 `build_context` 掃描
  「其他仍在 proposed 佇列中的提案」的 `HAS_EFFECT` 邊建立;`service.py::list_groups` 只列
  `status='proposed'`;`_approved_labels` 只補 label,**不補** `effect_to_hormone`。
- **實測:**

  ```text
  A（效果組仍待審）  : 胰島素與升糖素透過方向相反的兩個調控效果，在血糖上呈現拮抗。
  B（效果組已核准）  : 降血糖與升血糖透過方向相反的兩個調控效果，在血糖上呈現拮抗。
  ```

  但第六道防線**強制**效果組先核准,所以專家在**唯一能核准交互作用組的時點**看到的必然是 B——
  一句幾近同義反覆、且不指名激素的敘述。
- **違反的要求:** `group_statements.py:64-67` docstring 宣稱「The expert lens is built for this —
  its antagonism rule looks the hormone behind each effect up in context」。此宣稱僅在效果組**尚未**
  核准時成立,而那正是交互作用組**不能**核准的時候。
- **影響:** 專家 gate 的判斷依據(那句話)在主線路徑上品質下降。無測試覆蓋「先核准效果、再看交互
  作用組的 understanding」。
- **有界的修正方向:** 讓 `list_groups` 的 ctx 也從 approved 圖補 `effect_to_hormone`(可沿用既有的
  `_approved_labels` 那一趟查詢擴充),或修正 docstring 的宣稱並記錄為已知後果。

**M3 — `proposed_groups` 不是插入列數,重跑會虛報**

- **證據/位置:** `load_postgres.py` 中 `staged_groups += 1` 發生在任何 `INSERT` 之前,且不受
  `ON CONFLICT DO NOTHING` 影響;而同一函式的 docstring 寫「the counts are rows *actually* inserted
  — duplicates hit `ON CONFLICT DO NOTHING` and are excluded, so callers can report an honest
  proposed-count」。
- **影響:** 重新匯入同一章節時,`stats` 會回 `proposed_nodes: 0, proposed_edges: 0,
  proposed_groups: N`——對 owner 而言就是「新增了 N 組待審」,但佇列一列都沒增加。
  `docs/api_contract.md` 只寫「新增 `proposed_groups` 欄位」,未定義語意,無法據以辨義。
- **測試落差:** `test_re_ingest_does_not_duplicate_the_review_queue` 明確斷言
  `proposed_nodes == 0` 與 `proposed_edges == 0`,**唯獨略過** `proposed_groups`——落差正好落在
  未被斷言的那一項。
- **有界的修正方向:** 只在該組**確有列被插入**時才 `staged_groups += 1`;並在測試補上
  `second.stats["proposed_groups"] == 0`。或者改為在 docstring 與 `api_contract.md` 明確定義
  `proposed_groups` 為「本次涵蓋的群組數」而非「新增數」——但那會與同一個 `stats` 內另外兩個欄位的
  語意不一致,不建議。

**M4 — 測試 teardown 的刪除範圍超出測試自身足跡,會清掉真實待審提案**

- **證據/位置:** `ingestion/tests/test_document_ingest.py::_cleanup` 新增
  `DELETE FROM curation_items WHERE proposed_by = 'llm'`——**無 doc/group 範圍限定**。
- **影響:** 測試跑在與應用相同的 Postgres(`docker compose run --rm backend pytest`)。開發機上若有
  真實抽取產生、正在等待專家審閱的提案(這正是本變更製造出來的東西),`make test` 會**無聲刪光**。
  審閱佇列是本專案治理敘事的核心資產,teardown 不應有這種權限。同檔案其餘刪除全都以 `DOC_ID` 限定,
  這一行是唯一的例外。
- **有界的修正方向:** 改為以本測試的 group 前綴限定,例如
  `DELETE FROM curation_items WHERE group_id LIKE 'group:llm:' || $1 || '%'`(`$1` = `DOC_ID`),
  與檔內既有的 `doc_id` 限定風格一致。

### Low

**L1 — `approve_group` 的 docstring 仍只列四道 guard,新增的兩道未入列**

`service.py:441-456` 的編號清單止於「4. no member id already exists in the approved graph」,
而 `CHANGE_REPORT.md` 與 `api_contract.md` 都稱新 guard 為「第六道防線」。同一次改動加了 guard 卻沒更新
就在其正上方的 guard 清單,是最容易漂移的一種文件債。修正方向:在該清單補列 5(空端點 422)與
6(端點不存在 409)。

**L2 — `_fetch_approved_ids` 是無上限全圖掃描**

`runner.py` 的 `MATCH (n) WHERE n.status = 'approved' RETURN n.id` 沒有 `LIMIT`,與相鄰的
`_fetch_existing_concepts(neo4j_driver, max_existing)` 有界的作法不一致。目前規模無實害
(展示用圖),但這是每次 ingest 都會做一次的全表讀取。修正方向:若要保留,在 docstring 註明
「刻意無上限,因為漏掉一個 id 會導致重複提案」;若要有界,則需說明超限時的降級行為。

**L3 — `approved_ids` 錯誤時的失效是無聲的(直接回答 reviewer 提問 3)**

預設路徑本身是安全的:`_fetch_approved_ids` 的 Cypher 明確過濾 `status = 'approved'`,不會把 proposed
算進去,`neo4j_driver is None` 也正確退回空集合。真正的殘餘風險不在「呼叫端傳錯」,而在**傳錯之後
沒有任何痕跡**:`stage_extraction_output` 的
`if not nodes and not edges: continue` 會讓一個「全部節點都被認定為已核准」的群組**整組消失**,
既不計入 `staged_groups`,也不寫 log、不進 `IngestReport`。若 `approved_ids` 過寬,結果是佇列裡少了
一個陳述,而 `stats` 完全看不出來。修正方向:該 `continue` 分支至少要留下可觀測的痕跡
(計入一個 `skipped_groups` 欄位,或寫進 `ingestion_jobs` 的 stats),讓「少提案」變成可稽核事件而非
靜默行為。

### Suggestion

- **S1:** `stage_extraction_output` 過濾了已 approved 的**節點**,但沒有過濾已 approved 的**邊**。
  今天靠 `ON CONFLICT (item_id) DO NOTHING` 掩蓋(item_id 相同),行為正確;但一旦 `group_id` 推導規則
  改變,同一條已核准的邊就會以新 item_id 重新提案,並在核准時撞上第四道防線(成員 id 已存在)而 409。
  值得在 docstring 註明這個對稱性缺口是刻意的。
- **S2:** `docs/api_contract.md` 新增的表格把 `group_id` 形態寫成
  `group:llm:{chunk_id}:{anchor_id}`,但 `anchor_group_id` 產生的實際字串含冒號(例如
  `group:llm:doc:x:0:regulatory_effect:lower_bg`),對任何以 `:` 切分 group_id 的消費端都是陷阱。
  建議在契約上明記 group_id 只能整體比對,不得解析。

## Requirement and Test Coverage Gaps

| AC | 驗證報告的宣稱 | 本次審查的判定 |
|---|---|---|
| AC1 / AC1b(切分、巢狀 anchor) | Pass | **成立**,測試對得上實作,反向驗證可信 |
| AC1c(端點 guard 409、無回歸) | Pass | **部分成立**:409 路徑有測試,但「不誤擋合法群組」的回歸測試只涵蓋 `GROUP_OK`(邊全在組內),**未涵蓋殘餘組**——B1 就落在這個缺口 |
| AC2(殘餘組) | Pass | **不足**:三個殘餘測試的殘餘節點都與 anchor 組無交集,沒有一個讓殘餘邊指向被收走的節點 |
| AC3(群組可見、gate 與句子正確) | Pass | **成立**,但「句子正確」只在效果組仍待審時驗證(M2) |
| AC4(已核准只引用) | Pass | 成立;失效無聲的部分見 L3 |
| AC5(重跑冪等) | Pass | 佇列列數/組數確實不增(成立);但 `proposed_groups` **統計**不冪等且未被斷言(M3) |
| AC6 / AC7 | Pass | 未重跑,接受既有證據 |
| AC8(前端) | Partial(owed) | 自陳誠實。另注意前端新文案「已核准的概念只會被引用,不會請你重新核准一次」對使用者是真的,但沒有提及**順序依賴**——在 B1/R6 下使用者會遇到 409 卻無預期 |

**未被任何測試覆蓋的路徑:**

1. 殘餘邊指向被 anchor 組收走的節點(B1)。
2. 殘餘組落入 `back_translation` 的 P2 分支(H2)。
3. 先核准效果組、再檢視交互作用組的 `understanding`(M2)。
4. 重跑後的 `proposed_groups` 值(M3)。
5. anchor ─`HAS_EFFECT`→ anchor 的歸屬(M1)。

## Compatibility, Security, and Scope Assessment

- **安全:** 未發現新的注入面。第六道防線的 `_existing_approved_ids` 全走參數化 Cypher;型別白名單
  驗證仍在 `create_group` 的提案時執行,本變更未繞過。抽取路徑的 staging **不**經過
  `_validate_curation_payload`,但其上游 `validate_extraction_output` + 核准時的 gate 仍在,
  與變更前一致,非本次引入的回歸。
- **`status='approved'` 不變式:** 未被破壞。新 guard 只讀 approved 節點,不寫。抽取路徑不寫 Neo4j
  (AC6)已由端到端證據支持。
- **離線姿態:** `_fetch_approved_ids` 在 `neo4j_driver is None` 時回空集合,離線分支明確,符合
  CLAUDE.md 的離線可跑要求。
- **契約相容性:** `stage_extraction_output` 的簽章與回傳 arity 都改了(4-tuple → 5-tuple,新增兩個
  必要位置參數)。已確認唯一呼叫端是 `runner.py`,已同步。`stats` 新增鍵為向後相容的加法。
- **範圍:** 四項偏離在 `CHANGE_REPORT.md` 中皆已揭露,`approve_group` 的擴大範圍在 Plan revision 3
  有明確的 owner 批准紀錄(Plan:32、122、137-138、380)。**未發現未揭露的越界修改。**
  `docs/notes.md` 未追蹤且未進 commit,與提問 4 的說明一致——已確認 `git log --stat` 三個 commit
  均不含該檔,**無需處置**。
- **Rollback:** Plan 有 Rollback 段落。本變更無 migration、無新 production dependency,回退為單純
  `git revert`;唯一的持久副作用是已 staged 的 `group:llm:*` 列,回退後會殘留在
  `curation_items`(不影響檢索,因為從未進 Neo4j)。此點 Plan 未明說,建議補記。

## Unreviewed Areas and Residual Risk

- **未重跑測試套件**:接受 `VERIFICATION_REPORT.md` 的 186 passed 紀錄,未獨立複現。
- **未檢視前端呈現**:`app.js` 的 diff 僅為文案,已讀;但群組審閱頁如何呈現一個 409 失敗的核准
  (錯誤訊息是否可讀、是否引導使用者)未經審查,而 B1 讓這條路徑變得常見。
- **未評估抽取語意品質**(`CHANGE_REPORT.md` R7 / N1、N2)——已明確排除於本次範圍,同意其排除。
- **未執行 CI**;未驗證 `make eval` 的門檻。
- **殘餘風險:** B1 與 H2 都源自同一個設計盲點——切分規則只對齊了兩個 gate 之一
  (`engineer_gate`),沒有對齊 `back_translation`。修 B1 的表面症狀(補回懸空端點)不會自動解決
  H2(殘餘組仍可能裝兩個陳述)。建議把兩者當成同一個問題處置。

## Human Disposition Required

- **B1** 建議在合併前處置:它讓一個常見形態的群組在正常審閱流程中變成無出口的死結,而本變更的
  目的正是讓抽取結果可審閱。
- **H2** 需人類決定範圍:修正牽涉 `back_translation`,依 Plan 第 165 行屬 stop condition,
  不得由實作者自行納入。
- **M1–M4、L1–L3、S1–S2** 可由 owner 決定納入本次或另開 change。
- 未完成的瀏覽器確認(AC8)仍為 owed,與本審查的發現獨立。

The reviewer does not approve, fix, merge, or release this change.

---

# Verification Round 2 — 修正後複核(2026-08-11)

## Scope

複核對象:**未提交的工作區變更**(`git status`:9 個 modified、3 個 untracked)。基準
`f4af033`,共 +360 / −84。決策依據為新增的 `DECISION_INVENTORY_R2.md`(計畫 revision 4)。

## Verdict

**B1 與 H2 的主要症狀確實修好了,修法是對的(模板法),而且是我原報告沒想到的更好解法。
M1/M3/M4/L1/L3/S1/S2 全數處置且處置得當。但有一個原報告沒抓到、且本輪處置決策**低估**了的
問題(V1),以及一個 H2 的殘餘形態仍然活著(V2)。**

## Commands Executed(本輪,離線姿態)

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
  → 194 passed in 76.82s          （修正前 186;新增 8 個測試）
docker run --rm ghcr.io/astral-sh/ruff:0.15.21 check  (LINT_PATHS)  → All checks passed!
docker run --rm ghcr.io/astral-sh/ruff:0.15.21 format --check       → 102 files already formatted
mypy backend/app ingestion scripts                                  → Success: 79 source files
```

未跑 `app.eval.runner`(本輪未觸及檢索路徑);未跑 CI(未 push);瀏覽器確認仍 owed。

## 逐項複核

| 原 finding | 狀態 | 證據 |
|---|---|---|
| **B1** 殘餘懸空端點 | ✅ **已修** | 原 repro 重跑:三組 `DANGLING: []`;新增 `test_no_group_ever_carries_a_dangling_endpoint` 全域斷言 |
| **H2** 殘餘渲染 pattern 句 | ⚠️ **主症狀已修,殘餘形態仍在** | 同一 repro 的殘餘組現為 `pattern: P0`;P2 分泌陳述自成一組。但見 **V2** |
| **M1** source-wins | ✅ **已修** | `_GATE_ANCHOR_END` 依 gate 的 in/out 方向決定歸屬;`test_anchor_to_anchor_edge_lands_where_the_gate_reads_it` 釘住 `RE ─HAS_EFFECT→ RE` 歸目標端 |
| **M2** 交互作用句退化 | ❌ **未處置、未揭露** | `back_translation.py` 與 `service.py` 的 `effect_to_hormone` 皆未動;`DECISION_INVENTORY_R2.md` 的 I7 列了 M1/M3/M4/L1/L3/S1/S2,**獨缺 M2**,也未列入 deferred |
| **M3** `proposed_groups` 虛報 | ✅ **已修** | 改為 `staged_groups += group_rows > 0` |
| **M4** teardown 越界刪除 | ✅ **已修** | 改為 `group_id LIKE 'group:llm:' || $1 || '%'`(`$1`=DOC_ID) |
| **L1** docstring 缺 guard 5/6 | ✅ **已修** | |
| **L2** 全圖掃描 | ➖ 未處置(原即為 Low,可接受) | |
| **L3** 無聲少提案 | ✅ **已修** | 新增 `skipped_groups`,一路帶到 `stats` 與 `api_contract.md` |
| **S1 / S2** | ✅ **已註記** | docstring 註明邊不對稱過濾;契約註明 group_id 不得以 `:` 解析 |

模板法額外修好了我原報告沒發現的 **P3 被切斷**(`DECISION_INVENTORY_R2.md` F7)——這是本輪
grill 自己找出來的,判斷正確。

## 新 findings

### V1（High）— 共用節點跨組重複提案,任兩組只有先核准的那一組進得了圖譜

- **證據:** 原 B1 repro 重跑,同一個 chunk 切出三組,節點跨組重複提案的計數為
  `{'hormone:insulin': 3, 'physiological_variable:bg': 2}`。
  `stage_extraction_output` 為每組各寫一列 `item_id = curation:{group_id}:{node_id}`(不同組
  item_id 不同,`ON CONFLICT` 不會合併),所以三組各自帶著 `hormone:insulin` 的 `create` item。
- **機制:** `approve_group` 的**第四道防線**是無條件的——
  `clashes = existing["nodes"] + existing["edges"]; if clashes: raise 409`。核准第一組會把
  `hormone:insulin` 寫成 approved;核准第二組時它就成了「成員 id 已存在於 approved 圖」→ **409**,
  訊息為「approving would overwrite curated knowledge — resolve as an explicit update instead」。
- **影響:** 上述那個**完全普通**的血糖 chunk 切出三組、三組 gate 全 `pass`,但審閱者**最多只能核准
  其中一組**,而且無論先核准哪一組,另外兩組都變成 409。UI 上剩下的處置只有 reject 或 record-as-gap
  ——沒有「核准但跳過已存在的成員」這個動作。要讓其餘陳述進圖,只能改走
  `POST /admin/curation/groups` 手工重建一個剝掉共用節點的群組。
- **與 `DECISION_INVENTORY_R2.md` 的落差:** G6 已經預見這個後果(第 52–53 行),但把它定性為
  「G2 已接受的語意(退回重提),而非 B1 描述的無出口死結」。**這個定性低估了嚴重度**:
  (a) 它不是偶發,而是任何含「腺體分泌激素 + 該激素造成效果」的 chunk 的**常態**——即幾乎每個
  內分泌 chunk;(b) 它命中的是**gate 全過的正確陳述**,不是瑕疵提案,而「退回重提」要求專家駁回一個
  正確的陳述,再由人手工重建;(c) 修正 B1(殘餘帶端點)把重複面從「兩個 RE 共用一個變數」的偶發
  情形**擴大**成常態——這一點在 G6 的決策紀錄裡沒有量化。
  這是**既有缺陷**(自 `12887d2` 的共用變數情形起就存在,我第一輪也沒抓到),不是本輪引入的回歸;
  但本輪的修正確實放大了它。
- **有界的修正方向(需 owner 決定,牽涉 `approve_group` 語意):**
  (a) 第四道防線改為只對「**本組提案、且 payload 與 approved 版本不同**」的成員報 409,對內容相同的
      共用節點視為冪等 MERGE 放行;或
  (b) 核准時先剔除已 approved 的成員再寫入(等同把 `approved_ids` 的過濾從 staging 時挪到核准時,
      因為 staging 時的快照必然過期);或
  (c) 切分器不讓節點跨組——但那會直接推翻 AC1 與 G6,不建議。
  無論擇哪一項,都應補一個整合測試:同一 chunk 切出的兩組**依序核准都成功**。

### V2（High）— 模板內的多餘邊仍會讓成員「搭便車」,H2 的失效形態沒有完全消滅

- **證據(容器內純計算探測):**

  ```text
  A) 兩個 Hormone 各有一條 HAS_EFFECT 指向同一個 RegulatoryEffect
     group:llm:c1:regulatory_effect:bg_change
       members: [glucagon, insulin, bg, bg_change]   edges: [e:h1, e:h2, e:ov, e:dn]
       gate: pass | pattern: P1 | 「胰島素會造成一個調控效果：使血糖下降。」
                                   ↑ 升糖素完全沒被這句話描述，卻在同一組裡等著被核准

  B) 兩個 Structure 各有一條 SECRETES 指向同一個 Hormone
     group:llm:c1:hormone:x
       members: [x, v, 腺體A, 腺體B]                 edges: [e:r1, e:s1, e:s2]
       gate: pass | pattern: P2 | 「當變數V改變時，腺體A會分泌激素X。」
                                   ↑ 腺體B 同上
  ```

- **根因:** `_match_template` 的 `picked.extend(found)` 收下**所有**符合的邊,而模板的數量欄位
  (`needed`)只是**下限**;`render_understanding` 卻只描述 `has_effect[0]` / `secretes[0]`。兩者對
  「一則陳述有幾條這種邊」的假設不一致。
- **為何新守衛抓不到:** `test_a_residual_group_never_renders_a_pattern_sentence` 只檢查**殘餘組**;
  `test_every_template_renders_as_the_pattern_it_claims` 只餵**最小實例**(每種邊剛好一條)。
  多餘邊的形態落在兩個守衛的縫隙裡。
- **影響:** 這正是 `group_statements.py` 模組 docstring 自陳要防止的失效——「a group holding two
  statements shows the reviewer a sentence about one of them while the other rides along unseen into
  the approved graph」。範圍比原 H2 窄(需要重複的關係邊),但性質相同,且直接命中本專案的治理主張。
  **既有缺陷,非本輪引入**(舊實作的 `owned[anchor]` 同樣收下所有邊)。
- **有界的修正方向:** 加一個**跨組**的守衛,斷言「群組的每個成員節點都被渲染句提及」(或至少對
  template 組成立),讓這類缺口在測試層可見;修法上則是模板只認 `needed` 條、多餘的邊推入殘餘,
  或由 renderer 在數量超出它能描述的範圍時改判 `is_gap`。

### V3（Medium）— 「第五個 renderer pattern 出現時守衛會失敗」這個宣稱不成立

`backend/tests/unit/test_splitter_renderer_alignment.py` 的模組 docstring 寫
「it fails if a renderer pattern has no matching template」,`DECISION_INVENTORY_R2.md` G5 第 44–45 行
寫「未來新增第五個 renderer pattern 而未同步模板時,此守衛會失敗」。**兩者都不成立。**
`test_a_residual_group_never_renders_a_pattern_sentence` 的輸入完全由 `_INSTANCES` 組成,而
`_INSTANCES` 是與 `_TEMPLATES` 一起手寫的。新增一個**沒有模板、也沒有實例**的 renderer pattern 時,
它的形狀從未被餵進切分器,兩個守衛都不會失敗——正是 H2 當初漏掉 P2 的同一種盲區。
修正方向:改為從 `back_translation` 這一端列舉可回傳的 pattern 集合(`_ok(...)` 的第一個引數),
斷言它等於 `{t[0] for t in _TEMPLATES} | {P0, P5}`;或至少把 docstring 的宣稱降格為
「涵蓋已宣告的三個形狀」。

### V4（Low）— 模板優先序的無衝突是巧合,且 grill 自陳的待驗證項未被測試涵蓋

`DECISION_INVENTORY_R2.md` 第 115–116 行自陳:「未驗證是否存在兩個模板同時匹配同一批邊而順序影響
結果的形態;實作時須以測試涵蓋」。**實作未補這個測試。**
實際追查結果目前是安全的——P2 只吃 `SECRETES`／`REGULATES_SECRETION_OF`,P4 吃
`USES_EFFECT`／`ON_VARIABLE`(源自 Interaction),P1 吃 `HAS_EFFECT`／`ON_VARIABLE`(源自 RE)
／方向邊,邊型別與收斂端互斥,所以貪婪匹配不會餓死後面的模板。但這是**現有型別集合的巧合**,
沒有任何機制保證第四個模板加進來時仍成立。建議補一個測試斷言模板之間的邊型別×收斂端互斥,
或在 `_TEMPLATES` 上方註明這個前提。

### V5（Low）— `LIKE` 樣式中的 `_` 是萬用字元

`test_document_ingest.py::_cleanup` 的 `LIKE 'group:llm:' || $1 || '%'` 中,`DOC_ID`
(`doc:test_sample:ingest`)含底線,而 SQL `LIKE` 的 `_` 匹配任意單一字元,樣式因此略寬於預期。
實務上無害(不會匹配到別的真實 doc),但若要精確應加 `ESCAPE` 或改用 `starts_with`/`left()`。

## 文件與流程的落差(非程式碼)

1. **`CHANGE_REPORT.md` 與 `VERIFICATION_REPORT.md` 均未更新**(`git status` 顯示兩者未修改)。
   兩份報告目前描述的仍是修正前的行為:`CHANGE_REPORT.md` 仍寫「每個 `RegulatoryEffect` /
   `Interaction`…自成一組」(現已是模板法),Verification 仍寫 186 passed(現為 194),
   `stats` 的欄位清單也少了 `skipped_groups`。**依 CLAUDE.md 的 Definition of Done,
   「變更報告已產生,無未揭露偏差」目前不成立。**
2. **M2 既未修、也未列入 deferred**,`DECISION_INVENTORY_R2.md` 的 I7 直接略過它。這是**未揭露的
   範圍縮減**,需要一句明確的處置(修、或明列為 deferred 並說明理由)。
3. **全部變更仍未提交**(9 modified + 3 untracked)。`docs/notes.md` 依然是預期中的未追蹤檔。
4. Plan 已標為 revision 4 且記有 owner 批准(「開始實作」),與 `DECISION_INVENTORY_R2.md` 一致,
   流程上無瑕疵。範圍聲明(`approve_group` 僅動 docstring)與實際 diff **相符**。

## Human Disposition Required（第二輪）

- **V1** 建議在合併前處置:它讓「一個 chunk 切出的多則正確陳述」在正常流程中只有一則進得了圖譜。
  修法牽涉 `approve_group` 第四道防線的語意,超出目前批准範圍,**須 owner 決定**。
- **V2** 建議在合併前至少補上守衛(讓缺口在測試層可見),完整修法可另開。
- **V3、V4、V5** 可另開;但 **V3 建議一併修**,因為它讓「不會再犯同一個錯」這個保證失效。
- **M2** 需一句明確處置。
- **文件落差 1、2** 應在宣稱完成前補齊。

修正的方向與品質都好——模板法比我原報告建議的補洞式修法更根本,並額外找出 P3。
但**本輪不改變第一輪的結論:仍不建議合併。**

The reviewer does not approve, fix, merge, or release this change.

---

# Verification Round 3 — 複核(2026-08-11,commit `747f52e`)

## Scope

複核對象:`747f52e`(`f4af033..747f52e`,18 檔 +1409 / −117),工作區已無未提交變更
(僅 `docs/notes.md` 未追蹤,如預期)。

## Verdict

**V1–V5 五項全部修好,而且修得比我建議的更好——尤其 V3 的第三道守衛,是真正跳出「人工窮舉防人工
窮舉」迴圈的作法。commit message 主動撤回自己先前的不實宣稱,`CHANGE_REPORT.md` 也補了更正段落,
這在誠實揭露上是加分的。**

**但仍不建議合併,理由從技術面轉為治理面:這次動的是已批准 Contract 的核准語意,
`docs/api_contract.md` 沒有同步,現在載著一條**明確錯誤**的防線;而且這個改動超出 plan revision 4
自訂的範圍,沒有 revision 5、沒有決策紀錄、stop condition 未觸發。**

## Commands Executed（本輪,離線姿態）

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
  → 197 passed in 72.65s          （前一輪 194，本輪新增 3）
```

前一輪已驗的 ruff / mypy 未重跑(本輪未觸及格式面);`app.eval.runner`、CI、瀏覽器確認仍未由我複核。

## V1–V5 逐項複核

| finding | 狀態 | 我的驗證 |
|---|---|---|
| **V1** 共用節點導致「一段最多核准一組」 | ✅ **已修** | 第四道防線由「拒絕整組」改為「沿用已核准成員」。`node_writes`／`edge_writes` 排除已核准 id,`before_state.members_existed_in_graph` 與 `after_state.reused_nodes/reused_edges` 都入稽核。`test_approve_reuses_an_already_approved_member_without_rewriting_it` 直接斷言預寫 label `pre-existing` 在核准後**未被覆蓋**——這是關鍵斷言,寫對了 |
| **V2** 模板收下多餘同型邊 | ✅ **已修** | `picked.extend(found[:needed])`。實跑複現我原本的兩個案例:兩個 Hormone 指向同一 RE → 第二條 `HAS_EFFECT` 落殘餘,殘餘 `gate: fail_pattern` 並在 P0 句中**指名升糖素**;兩個 Structure 分泌同一 Hormone → 腺體B 同樣被誠實列出 |
| **V3** 守衛宣稱不實 | ✅ **已修,且修得對** | 新增 `test_every_pattern_the_renderer_can_answer_with_is_accounted_for`,以 `inspect.getsource(back_translation)` 掃出 pattern id,要求每個不是有模板就是列入 `_DELIBERATELY_UNTEMPLATED`(目前只有 P3,附理由)。並反向斷言豁免清單不得腐爛。這確實跳脫了原本的盲區 |
| **V4** 模板優先序未測 | ✅ **已修** | 新增 `test_no_edge_is_claimed_by_two_templates` 與 `test_interaction_and_effect_each_keep_their_own_on_variable`,測試自己註明「currently holds by luck of the type set」——誠實 |
| **V5** `LIKE` 的 `_` 萬用字元 | ✅ **已修** | 改用 `starts_with(group_id, ...)`,並註明理由 |
| **B1 / H2** 回歸 | ✅ 未回歸 | 原 repro 重跑:三組全 `DANGLING: []`,殘餘為 `P0` |
| **M2** 交互作用句退化 | ❌ **第三輪仍未處置、仍未揭露** | `back_translation.py` 最後一次變動遠早於本 change;`service.py` 無 `effect_to_hormone`。`TASK_LOG.md` 本輪列了 V1–V5,**仍未提及 M2** |

## 新 findings

### W1（Blocking）— 改了已批准 Contract 的核准語意,但契約文件沒同步,且超出批准範圍

**(a) `docs/api_contract.md` 現在載著一條明確錯誤的防線。** 核准端點的表格仍列:

```
| **成員 id 已存在於 approved 圖**（核准會 MERGE 覆蓋既有策展知識）— 必須改走明確的 update 決策 | `409 conflict` |
```

這個 409 **已經不存在**。同節的回應形狀仍寫 `{group_id, status:'approved', nodes, edges}`,
未含新增的 `reused_nodes` / `reused_edges`;小標題仍寫「核准前的**四道**防線」而表內有七列。
`docs/api_contract.md` 依 CLAUDE.md 是 Source of Truth,且本 change 的 **AC8 明文要求
「`api_contract.md` 同步」**——目前不成立。任何依這份契約行事的人(或未來的 agent)會得到錯的行為預期。

**(b) 這是 Contract 變更,且超出 plan revision 4 的自訂範圍。**
revision 4 的範圍聲明白紙黑字寫「`approve_group` **僅動 docstring**(L1)」;本 commit 改了它的
核准語意與回應形狀。CLAUDE.md 的 Stop Conditions 明列「**必須改變已批准的 Contract**」為應停止
回報的情況。查證結果:`IMPLEMENTATION_PLAN.md` 仍停在 **revision 4**
(`Approved plan revision: **4**`),`DECISION_INVENTORY_R2.md` 自我審查後**未新增任何關於核准語意的
決策紀錄**——G6 當時的立場恰恰相反,是「共用節點撞第四道防線是 G2 已接受的語意」。
也就是說:**一個被明確記錄為「已接受」的設計決定,在沒有新決策紀錄的情況下被推翻了。**

我要說清楚:**我認為這個技術判斷是對的**——「圖裡一個節點掛多條關係」確實是基本行為,舊防線
確實把「重用」誤當成「覆蓋」,而且新作法(跳過寫入)在保護策展文字上**嚴格優於**舊作法
(舊的擋得住整組,但一旦有東西被核准就照樣覆蓋)。問題不在判斷,在**這個判斷該由誰做**:
它推翻的是 owner 已記錄的決定,並改動 Source of Truth 契約。

- **有界的處置方向:** 補 plan **revision 5** 或一則決策紀錄(明載「G6 的立場被 V1 的實測推翻」),
  取得 owner 對契約變更的明確批准;同步更新 `api_contract.md` 的防線表(刪除該列、改寫為
  「已核准成員沿用而非重寫」)、回應形狀、以及小標題的「四道」。

### W2（Medium）— 「策展版本永遠優先」對**已停用(deprecated)**的節點不成立

- **證據:** `_existing_approved_ids` 只匹配 `status = 'approved'`。`delete_node` 走
  `_deprecate_node_in_neo4j`,把節點留在圖上並改為 `status='deprecated'`(`service.py:776-784`)。
  因此一個**曾被核准、後被刪除**的 id 不會進入 `reused_nodes`,會落入 `node_writes`,而
  `load_neo4j.write_nodes` 的 `MERGE … SET n.label/.status/.description/n += $props`
  會把它**改回 `approved` 並覆蓋策展文字**。
- **影響:** 核准一個含有已停用概念的群組,會**無聲地撤銷那次刪除決定**,並覆寫當初的策展措辭。
  這正是被移除的那道防線所要防的風險,在唯一沒被新作法涵蓋的那個狀態上仍然開著。
  edge 同理(`delete_edge` 亦為 deprecate)。
- **這是既有缺陷,非本輪引入**(舊防線同樣只看 approved,同樣會復活)。但本次 docstring 明確宣稱
  「Skipping the write removes that risk **outright** — the curated version **always** wins」,
  對 deprecated 狀態而言這句話是**不成立的**,而該宣稱正是這次改動的正當性基礎。
- **有界的修正方向:** 把重用判定從 `status='approved'` 放寬為「id 已存在於圖上」,或對 deprecated
  的成員明確報錯(復活必須是明示決定);至少要把 docstring 的「always」改成「對已核准成員」並記錄
  deprecated 這個缺口。

### W3（Medium）— 專家在決策當下不知道哪些成員會被沿用

`list_groups` 不計算、也不回傳「本組哪些成員已在已核准圖譜中」。專家看到的理解句由**提案的**
label 渲染,但真正留在圖上的是**策展版**。兩者若有出入,專家等於是對一段他看到、卻不會進入圖譜的
文字按下核准;稽核紀錄事後看得到(`reused_nodes`),但決策當下看不到。
舊行為在這個情境是 409(強迫成為明示決定),新行為是靜默沿用——這是這次修法真正的治理成本,
`TASK_LOG.md` 未提及。
**有界的修正方向:** 在 `list_groups` 的回應加一個「將被沿用的成員」清單,並在審閱面板標示;
或在核准回應／flash 中明講。

### W4（Low）— 前端未跟上新的回應形狀

`frontend/app.js` 的成功訊息仍為
`已核准並寫入知識圖譜(nodes ${res.nodes} / edges ${res.edges})`。`res.nodes` 現在**已扣除沿用的
成員**,所以一個三節點、其中一個沿用的群組會顯示「nodes 2」,畫面上沒有任何地方解釋少掉的那一個。
`reused_nodes` / `reused_edges` 未被使用。本 change 的瀏覽器確認本來就 owed,建議一併處理。

### W5（Low）— commit message 的一項驗證宣稱沒有對應的自動化測試

commit message 寫「Two approvals sharing a concept now both succeed, leaving one node with two
relationships」。測試套件裡沒有「連續核准兩個共用節點的群組」的測試——
`test_approve_reuses_an_already_approved_member_without_rewriting_it` 是以
`_write_approved_node` **預先寫入**一個已核准節點來覆蓋沿用路徑。
兩者在程式路徑上等價,所以**不是覆蓋缺口**,但 message 描述的那個具體情境(也正是 V1 的實際症狀)
只有手動實跑、沒有回歸測試釘住。建議補一個依序核准兩組的整合測試,讓 V1 不會靜默復發。

### W6（Suggestion）— 列舉守衛的正則有一個小前提

`re.findall(r'"(P\d+)"', source)` 依賴 pattern id 以**雙引號字面值**出現在 `back_translation` 中。
今天成立(ruff 統一雙引號),但若日後改用常數或 f-string 傳入 `_ok(...)`,守衛會靜默漏掉。
可考慮改為讀 `_ok` 呼叫的第一個引數,或在 `back_translation` 端宣告一個明確的 pattern id 常數表。
這是強化,不是缺陷。

## 文件與流程狀態（更新）

1. **`CHANGE_REPORT.md` / `VERIFICATION_REPORT.md` / `TASK_LOG.md` 均已更新**——上一輪的落差 1
   已解決。`CHANGE_REPORT.md` 新增的「更正」段落主動承認兩處先前的不實宣稱,並指出 `f4af033` 的
   commit message 含同一句、無法追溯修改故在此記錄——**這是應該被肯定的揭露品質**。
2. **上一輪落差 2(M2 未修也未列 deferred)仍然存在**,已連續兩輪未處置。
3. **新落差:`api_contract.md` 未同步核准語意變更(W1a),且該變更無決策紀錄與 plan 修訂(W1b)。**
4. 全部變更已提交於 `747f52e`,工作區乾淨。

## Human Disposition Required（第三輪）

- **W1** 建議在合併前處置,且**必須由 owner 決定**:它推翻了一個已記錄為「已接受」的設計決定,
  並改動 Source of Truth 契約。技術判斷我認同;需要的是補上批准與文件,不是回退程式碼。
- **W2** 建議一併修或明確記錄:它讓本次改動的核心宣稱(「策展版本永遠優先」)在一個真實狀態下不成立。
- **W3、W4** 建議與 owed 的瀏覽器確認一起處理。
- **W5、W6** 可另開。
- **M2** 已第三輪未處置,需要一句明確的「修」或「deferred + 理由」。

技術上,V1–V5 這一輪的修正品質高於前兩輪:根因找得準(問題在核准語意而非切分)、修法比症狀治療更
根本、並且主動撤回自己的錯誤宣稱。**剩下的阻礙不在程式碼,在治理紀錄與契約文件。**

The reviewer does not approve, fix, merge, or release this change.
