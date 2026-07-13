"""Provider-agnostic LLM gateway.

First version only wires OpenAI (per docs/api_contract.md section 5) plus an
offline deterministic fallback so the local Docker demo runs with no API key.
When we add a second provider we can extract a real interface; for now a single
module with a provider branch is enough.
"""

from app.core.config import settings
from app.llm.usage import TokenUsage

_ANSWER_MODEL = "gpt-4o-mini"

_ANSWER_SYSTEM_PROMPT = (
    "你是高中生物的助教。只根據提供的參考資料與知識圖譜三元組回答問題,"
    "不要編造未提供的內容。若資料不足,請明說。用繁體中文簡潔作答。"
)

_CHECK_SYSTEM_PROMPT = (
    "你是高中生物的助教,負責檢查學生的回答。根據提供的參考資料判斷學生回答是否正確,"
    "指出其中的錯誤觀念,並給出簡潔的繁體中文回饋。"
)


def _use_openai() -> bool:
    return settings.llm_provider == "openai" and bool(settings.openai_api_key)


# --- answer generation --------------------------------------------------------


def generate_answer(context: str, question: str) -> tuple[str, TokenUsage]:
    """Return ``(answer, TokenUsage)``; offline path reports zero tokens."""
    if _use_openai():
        return _openai_answer(context, question)
    return _fallback_answer(context, question), TokenUsage()


def _openai_answer(context: str, question: str) -> tuple[str, TokenUsage]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=_ANSWER_MODEL,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"參考資料:\n{context}\n\n問題:{question}"},
        ],
    )
    usage = TokenUsage(completion=response.usage.total_tokens if response.usage else 0)
    content = response.choices[0].message.content
    if not content:
        return "抱歉,目前無法產生回答,請稍後再試。", usage
    return content.strip(), usage


def _fallback_answer(context: str, question: str) -> str:
    if not context.strip():
        return "目前知識庫中找不到與此問題相關的內容,無法作答。"
    return "（離線示範模式:未設定 LLM,以下為依知識庫檢索結果整理的節錄)\n\n" + context.strip()


# --- misconception check ------------------------------------------------------


def check_misconception(
    context: str,
    question: str,
    student_answer: str,
    misconception_nodes: list[dict],
) -> tuple[dict, TokenUsage]:
    """Return ``({is_correct, misconceptions_detected, feedback}, TokenUsage)``."""
    if _use_openai():
        return _openai_check(context, question, student_answer, misconception_nodes)
    return (
        _fallback_check(context, question, student_answer, misconception_nodes),
        TokenUsage(),
    )


def _openai_check(
    context: str, question: str, student_answer: str, misconception_nodes: list[dict]
) -> tuple[dict, TokenUsage]:
    import json

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    known = [{"id": n["id"], "label": n["label"]} for n in misconception_nodes]
    user = (
        f"參考資料:\n{context}\n\n問題:{question}\n\n學生回答:{student_answer}\n\n"
        f"已知的常見錯誤觀念節點:{json.dumps(known, ensure_ascii=False)}\n\n"
        "請以 JSON 物件回覆,包含欄位:is_correct (boolean)、"
        "misconception_ids (上述清單中命中的 id 陣列)、feedback (繁體中文說明)。"
    )
    response = client.chat.completions.create(
        model=_ANSWER_MODEL,
        messages=[
            {"role": "system", "content": _CHECK_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    usage = TokenUsage(completion=response.usage.total_tokens if response.usage else 0)
    try:
        parsed = json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        parsed = {}
    hit_ids = set(parsed.get("misconception_ids", []))
    detected = [n for n in misconception_nodes if n["id"] in hit_ids]
    return {
        "is_correct": bool(parsed.get("is_correct", False)),
        "misconceptions_detected": detected,
        "feedback": parsed.get("feedback", ""),
    }, usage


def _fallback_check(
    context: str, question: str, student_answer: str, misconception_nodes: list[dict]
) -> dict:
    """Heuristic offline check: flag a misconception if its label keywords appear
    in the student's answer; otherwise gauge correctness by overlap with context.
    """
    detected = [
        n
        for n in misconception_nodes
        if any(tok and tok in student_answer for tok in n["label"].split())
    ]
    if detected:
        labels = "、".join(n["label"] for n in detected)
        return {
            "is_correct": False,
            "misconceptions_detected": detected,
            "feedback": f"（離線示範模式)回答中可能涉及常見錯誤觀念:{labels}。請對照參考資料再確認。",
        }

    from app.db.chunks import _bigrams  # local import to avoid a cycle at module load

    overlap = len(_bigrams(student_answer) & _bigrams(context))
    is_correct = overlap >= 3
    verdict = "方向大致正確" if is_correct else "與參考資料的關聯不足,建議再補充"
    return {
        "is_correct": is_correct,
        "misconceptions_detected": [],
        "feedback": f"（離線示範模式)未設定 LLM,以關鍵詞比對粗略判斷:{verdict}。",
    }
