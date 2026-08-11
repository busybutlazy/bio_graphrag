# Decision Inventory — 第二輪 grill（切分單位重新定義）

## Scope

獨立審查（`REVIEW_REPORT.md`）的 B1／H2 顯示切分規則只對齊了兩道 gate 中的一道。本輪重新定義
「一個切分單位」，使其涵蓋 `back_translation` 的四個 pattern。範圍限於切分規則本身；
不含抽取語意品質（N1／N2）與 backlog 生命週期（DF1）。

會期：2026-08-11。分支 `feat/extract-per-group-staging` @ `f4af033`（已 push，**不得合併**）。

## Decisions

### F7 — `back_translation` 有四個 pattern，形狀各異（事實）

| Pattern | 形狀 | 收斂點 | 現行切分後 |
|---|---|---|---|
| P1 single_regulatory_effect | `Hormone ─HAS_EFFECT→ RE ─ON_VARIABLE/方向→ Var` | `RegulatoryEffect` | ✅ 正確 |
| P2 secretion_trigger | `Var ─REGULATES_SECRETION_OF→ Hormone` + `Structure ─SECRETES→ Hormone` | **Hormone（無 anchor 型別）** | ❌ 永遠落殘餘 |
| P3 regulatory_effect_with_mechanism | P1 + `Hormone ─CAUSES→ Process` | RE，但 `CAUSES` 掛在 Hormone | ❌ 機制被切斷 |
| P4 antagonistic_interaction | `Interaction ─USES_EFFECT→ RE×2, ─ON_VARIABLE→ Var` | `Interaction` | ✅ 正確（T1b 後） |

- Evidence: `back_translation.py:73-130` 依序 return（先命中先返回）；實測複現於本輪。
- Affected scope: 「anchor = 特定節點型別」這個前提不成立——收斂點不一定有特殊型別
  （P2），也不一定只吃收斂點自己的邊（P3）。

### F8 — 兩個症狀同源（事實）

審查的 B1（殘餘帶懸空端點）與 H2（殘餘渲染出 pattern 句）皆源於 F7：完整的分泌陳述無處可去，
只能落進殘餘桶，於是殘餘同時（a）裝著別組收走節點的邊，（b）自己撞上 P2 而被描述成一句。
實測輸出見 `REVIEW_REPORT.md` B1／H2 及本輪複現。

### F9 — `ingestion` 不得 import `backend`（事實，架構限制）

pattern 的權威定義在 `backend/app/graph/back_translation.py`，但依賴方向是單向的
（backend → ingestion）。因此切分器要懂 pattern，只能是「模板寫在 ingestion」或「改動 renderer」。

### G5 — 切分單位的定義方式
- Classification: user-owned — **RESOLVED**（owner，2026-08-11）
- Resolution: **在 `ingestion` 宣告式地寫出 pattern 模板**（收斂點型別 + 必要邊型別與方向），
  依 renderer 的優先序 P2 → P4 → P1 貪婪匹配，未被任何模板吃掉的元素歸殘餘。
  **不改 `back_translation`**（避開 stop condition，也不動 gold regression 的打擊對象）。
- 一致性以**兩個行為守衛**維持（非解析原始碼）：
  1. 每個模板的最小實例送進 `render_understanding` 必須回傳對應 pattern；
  2. **殘餘組永遠不得渲染出 pattern 句**（`pattern ∈ {P0, P5}`）——直接釘住 H2，
     且未來新增第五個 renderer pattern 而未同步模板時，此守衛會失敗。
- Rationale: 選項 b（定義下移、renderer 讀它）是更乾淨的單一來源，但要改 `back_translation`
  且風險高；選項 c（只補 P2／P3 特例）是騙點式修補，第五個 pattern 出現時會再次靜默壞掉。

### G6 — 殘餘邊的懸空端點（審查 B1）
- Classification: user-owned — **RESOLVED**，但**後半段已被推翻**（見下）
- Resolution: **殘餘邊連同其端點節點一起納入殘餘組**，與 anchor 組的規則一致，懸空從結構上消失。
- ~~已知並接受的後果：共用節點會在兩組重複提案，後核准者撞第四道防線（成員 id 已存在）→ `409`。
  這是 **G2 已接受的語意**（退回重提），而非 B1 描述的無出口死結。~~

> **推翻（2026-08-11，第二輪審查 V1 之後）。** 上面刪除線那段的定性是**錯的**，錯在低估頻率而非
> 低估嚴重性。實測:一個普通的血糖 chunk 切出三組，共用「胰島素」（3 組）與「血糖」（2 組）；
> 核准第一組後其餘組**全部 409**，審閱者一段課文最多只能核准一個陳述，不管先核准哪一個。
> 這不是「偶發的退回重提」，是功能實質不可用。
>
> 真正的根因不在切分層，而在核准語意:那道防線把**節點重用**誤當成**覆蓋策展知識**。圖上一個節點
> 掛多條關係是最基本的行為，`write_nodes` 的 `MERGE` 本來就冪等；真正的覆蓋風險只在它後面那句
> 無條件的 `SET n.label/.description`。
>
> **新決定**:已存在於 approved 圖的成員**沿用不重寫**（策展版本永遠優先），並新增一道防線擋下
> 「重新提出已被刪除（`deprecated`）的知識」。詳見 `IMPLEMENTATION_PLAN.md` revision 5——
> 三項 Contract 變更已由 owner 於 2026-08-11 逐項確認後批准。
>
> 這也解釋了為什麼 B1 與 V1 看似矛盾:它們是同一個錯誤前提的兩面。前提是「群組是一袋要建立的東西」，
> 而正確的理解是「**邊是主張，節點是主張用到的詞彙**」——沒有人「擁有」一個節點。

### G7 — P3（含機制的調控）不是切分單位
- Classification: user-owned — **RESOLVED**（owner 領域判斷）
- Resolution: **機制與效果分開審**。模板集涵蓋 P1／P2／P4；`Hormone ─CAUSES→ Process` 不被
  P1 模板吃入，落入殘餘（渲染 P0）。
- Consequence（須寫入文件）：**`back_translation` 的 P3 在抽取路徑上不會被觸發**——它的前提是
  機制與效果同在一個 proposal 內。P3 仍適用於手工提案。

### I6 — 模板匹配的優先序與重疊處理（實作預設）
- Classification: implementation-owned
- Default: 依 renderer 的 return 順序 P2 → P4 → P1 匹配；一條邊只能屬於一組（維持現行不變式）；
  節點可跨組（G2／G6 已接受）。已被前一個模板吃掉的**邊**不再參與後續匹配。

### I7 — 審查的其餘 finding（實作預設，隨本次一併修）
- Classification: implementation-owned
- M1 `_edge_owner` 的 source-wins：改為依 gate 檢查該邊的方向決定歸屬（out-edge → source，
  in-edge → target），並補 anchor─`HAS_EFFECT`→anchor 的測試釘住行為。
- M3 `proposed_groups` 改為只在該組確有列被插入時才 +1；測試補斷言重跑為 0。
- M4 測試 teardown 的 `DELETE FROM curation_items` 加上 `DOC_ID` 範圍限定。
- L1 `approve_group` docstring 補列第 5、6 道 guard。
- L3 `if not nodes and not edges: continue` 改為可觀測（計入 `skipped_groups`）。
- S1 docstring 註明「只過濾已核准的節點、不過濾邊」是刻意的。
- S2 `api_contract.md` 註明 `group_id` 只可整體比對、不得以 `:` 解析。

## Inventory Coverage

- Areas examined: `back_translation.py` 四個 pattern 全文、`engineer_gate._pattern_check`、
  `group_statements.py`、`schema/relationship_types.md` 建模原則、審查報告全部 finding、
  容器內純計算複現（B1／H2／P3 三個症狀）。
- Known gaps: 未窮舉 LLM 可能產出的所有形狀；模板法對「部分符合」的形態（例如缺一條邊的 P2）
  的行為需在實作時定義並測試——預設應與現行一致（成組後由 gate 判 `fail_pattern`）。
- Last checked: 2026-08-11，分支 @ `f4af033`。

---

# Decision Readiness Summary

Status: **Ready**

## Resolved Decisions

G5（模板法 + 兩個行為守衛，不動 renderer）、G6（殘餘邊帶端點）、G7（P3 不是切分單位）。

## Implementation-Owned Defaults

I6（匹配優先序與重疊）、I7（審查其餘 finding 的處置方向）。

## Intentionally Deferred Decisions

無新增。既有的 DF1／DF2 不受本輪影響。

## Blocking Open Decisions

None

## Conflicts or Assumptions Found

- **審查的 H2 判定正確，且不完整**：本輪額外發現 **P3 也被切壞**（機制被切斷丟進殘餘）。
  四個 pattern 壞了兩個，不是一個。
- **`CHANGE_REPORT.md` 有一句錯誤宣稱**：稱殘餘組「一律走 P0 plain summary」。實測為 P2。
  該句須在修正時一併更正。
- 假設：模板依 renderer 的 return 順序匹配即可，未驗證是否存在兩個模板同時匹配同一批邊而順序
  影響結果的形態；實作時須以測試涵蓋。

## Updated Artifacts

- 新增本檔。未修改任何實作檔。

## Recommended Next Workflow

**Ready for plan-change**（計畫 **revision 4**）——範圍：切分器改為模板法（G5／G6／G7）
＋ 審查 finding M1／M3／M4／L1／L3／S1／S2。
不含：抽取語意品質（N1／N2）、backlog 生命週期（DF1）、`back_translation` 任何改動。
