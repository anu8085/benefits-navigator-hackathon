"""Follow-up question generation and answer application for the Family Navigator."""
from __future__ import annotations
import json
import re

from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_AVAILABLE

_FOLLOWUP_SYSTEM = """\
You are a benefits navigator assistant for families in India.
Given a family's extracted profile, generate 2-3 follow-up questions to fill in missing information.

Return ONLY a valid JSON array — no markdown fences, no preamble, no explanation.
Each element must be a JSON object with exactly these keys:
  "id"       — short snake_case identifier (e.g. "insurance", "urgency", "travel_distance")
  "question" — question text (plain English, simple enough to read aloud)
  "type"     — "radio" or "text"
  "options"  — list of option strings for radio questions, or [] for text questions

Rules:
- Return EXACTLY 2-3 question objects.
- If pincode is null or missing, make the first question a "text" type asking for it.
- Ask about health insurance status if not clearly stated in the description.
  Use options: ["Yes, I have insurance", "No, I don't have insurance", "Not sure"]
- Ask about travel distance preference if a pincode is known.
  Use options: ["Up to 5 km", "Up to 10 km", "Up to 25 km"]
- Ask about urgency.
  Use options: ["Urgent — I need help today", "Routine — planning ahead"]
- Do NOT mention any government scheme names (no Ayushman Bharat, ICDS, JSY, PMMVY, etc.).
- Keep all question text simple and plain.
"""


def _deterministic_questions(profile: dict, raw_text: str = "") -> list[dict]:
    """Return 2-3 deterministic follow-up questions based on what is missing or unclear."""
    questions: list[dict] = []
    raw_lower = (raw_text or "").lower()

    # Priority 1 — location: pincode unknown
    if not profile.get("pincode"):
        questions.append({
            "id": "pincode",
            "question": "What is your pincode or nearest town/district?",
            "type": "text",
            "options": [],
        })

    # Priority 2 — insurance: not explicitly mentioned in the description
    insurance_clear = any(
        kw in raw_lower
        for kw in ("insur", "uninsured", "no coverage", "have coverage")
    )
    if not insurance_clear and len(questions) < 3:
        questions.append({
            "id": "insurance",
            "question": "Do you currently have health insurance coverage?",
            "type": "radio",
            "options": ["Yes, I have insurance", "No, I don't have insurance", "Not sure"],
        })

    # Priority 3 — travel distance: useful for facility recommendations when location known
    if profile.get("pincode") and len(questions) < 3:
        questions.append({
            "id": "travel_distance",
            "question": "How far can you travel to reach a health facility?",
            "type": "radio",
            "options": ["Up to 5 km", "Up to 10 km", "Up to 25 km"],
        })

    # Priority 4 — urgency: always a useful planning signal
    if len(questions) < 3:
        questions.append({
            "id": "urgency",
            "question": "Is this urgent today, or are you looking for routine support?",
            "type": "radio",
            "options": ["Urgent — I need help today", "Routine — planning ahead"],
        })

    return questions[:3]


def generate_followup_questions(profile: dict, raw_text: str = "") -> list[dict]:
    """Return 2-3 follow-up question dicts. Claude-first, deterministic fallback."""
    if CLAUDE_AVAILABLE:
        try:
            import anthropic

            user_msg = (
                f"Family profile extracted from their description:\n"
                f"{json.dumps(profile, default=str, indent=2)}\n\n"
                f"Original description: {raw_text[:500]}\n\n"
                "Generate 2-3 follow-up questions as a JSON array."
            )

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=400,
                system=_FOLLOWUP_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            raw_resp = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

            # Strip markdown fences if Claude wrapped the JSON
            raw_resp = re.sub(r"^```[a-z]*\n?", "", raw_resp, flags=re.MULTILINE)
            raw_resp = re.sub(r"\n?```$", "", raw_resp.rstrip()).strip()

            parsed = json.loads(raw_resp)
            if isinstance(parsed, list) and 1 <= len(parsed) <= 5:
                validated: list[dict] = []
                for item in parsed[:3]:
                    if isinstance(item, dict) and "id" in item and "question" in item:
                        validated.append({
                            "id": str(item.get("id", "q")),
                            "question": str(item.get("question", "")),
                            "type": str(item.get("type", "radio")),
                            "options": list(item.get("options", [])),
                        })
                if validated:
                    return validated
        except Exception:
            pass

    return _deterministic_questions(profile, raw_text)


def apply_followup_answers(
    profile: dict,
    questions: list[dict],
    answers: dict[str, str],
) -> dict:
    """Merge follow-up answers into a copy of the profile and return the updated copy."""
    updated = profile.copy()

    for q in questions:
        qid = q["id"]
        ans = answers.get(qid) or ""
        if not ans:
            continue
        ans_lower = ans.lower().strip()

        if "pincode" in qid or "location" in qid:
            candidate = ans.strip()
            if re.fullmatch(r"\d{6}", candidate):
                updated["pincode"] = candidate

        elif "insurance" in qid:
            if re.match(r"no\b", ans_lower):
                updated["uninsured"] = True
            elif re.match(r"yes\b", ans_lower):
                updated["uninsured"] = False
            # "Not sure" → leave profile unchanged

        elif "urgency" in qid or "urgent" in qid:
            updated["urgency"] = "urgent" if "urgent" in ans_lower else "routine"

        elif "travel" in qid or "distance" in qid:
            # Check longest match first to avoid "5" matching "25"
            for km_str in ("25", "10", "5"):
                if km_str in ans:
                    updated["travel_km"] = int(km_str)
                    break

        elif "pregnancy" in qid or "pregnant" in qid:
            if "recently" in ans_lower or "delivered" in ans_lower or "postnatal" in ans_lower:
                updated["pregnant"] = False
                updated["recently_delivered"] = True
                updated["adult_woman"] = True
            elif "pregnant" in ans_lower:
                updated["pregnant"] = True
                updated["recently_delivered"] = False
                updated["adult_woman"] = True
            else:
                updated["pregnant"] = False
                updated["recently_delivered"] = False

        elif "child" in qid and "age" in qid:
            m = re.search(r"(\d+)\s*(?:month|mo)", ans_lower)
            if m:
                months = int(m.group(1))
                updated["child_age_months"] = months
                updated["child_under_5"] = months < 60
            else:
                m2 = re.search(r"(\d+)\s*(?:year|yr)", ans_lower)
                if m2:
                    months = int(m2.group(1)) * 12
                    updated["child_age_months"] = months
                    updated["child_under_5"] = months < 60

    return updated
