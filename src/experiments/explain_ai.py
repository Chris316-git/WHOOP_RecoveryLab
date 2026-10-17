"""Plain-language explanation of a finished experiment by the LLM. The statistics, the verdict
and the recommended next step are computed in code; the model only explains them, every number
it uses must come from the result, and the code-written explanation is the fallback."""
import json
from collections.abc import Callable

from src.llm.wording import call_claude
from src.reasoning.validate import BANNED, _numbers

MAX_CHARS = 600
SYSTEM = """You explain the result of a personal experiment to the person who ran it.
You receive the result as JSON, computed in code: the habit tested, the outcome, the effect with a 95% interval,
the number of pairs of nights, the randomization test p-value, how many treatment nights they confirmed, the
verdict and the recommended next step.

Write 3 or 4 short, plain sentences: what was tested, what the numbers show, how sure we can be (the interval and
adherence), and the recommended next step. The verdict is final: do not upgrade or downgrade it. Use only numbers
from the input, copied exactly. Results apply to this person only. No medical claims, no emojis.
Reply with JSON only: {"message": "..."}"""


def result_input(result: dict, spec: dict) -> dict:
    p, s = result["primary"], result["secondary"]
    return dict(habit=spec["title"], question=spec["question"],
                outcome=dict(label=p["label"], unit=p["unit"], smallest_meaningful_effect=p["meaningful"],
                             verdict=p["itt"]["verdict"], effect=p["itt"]["effect"], interval_95=p["itt"]["ci"],
                             pairs=p["itt"]["pairs"], randomization_p=p["itt"]["p"],
                             confirmed_nights_only=p["per_protocol"]),
                secondary=dict(label=s["label"], unit=s["unit"], effect=s["itt"]["effect"],
                               interval_95=s["itt"]["ci"]),
                adherence=result["adherence"], recommended_next_step=result.get("recommended"))


def explain_result(result: dict, spec: dict, api_key: str, model: str,
                   call: Callable[..., str] | None = None) -> tuple[str | None, str]:
    data = result_input(result, spec)
    try:
        text = (call or (lambda k, m, d: call_claude(k, m, d, system=SYSTEM)))(api_key, model, data)
        start, end = text.find("{"), text.rfind("}")
        message = str(json.loads(text[start:end + 1])["message"]).strip()
    except Exception as exc:
        return None, f"template ({type(exc).__name__})"
    if not message or len(message) > MAX_CHARS:
        return None, "template (length)"
    if _numbers(message) - _numbers(json.dumps(data)):
        return None, "template (numbers)"
    if any(w in message.lower() for w in BANNED):
        return None, "template (wording)"
    return message, "llm"
