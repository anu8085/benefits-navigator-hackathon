"""Tests for follow-up question generation and answer application."""
import pytest


DEMO_TEXT = (
    "I live in pincode 560001. I am pregnant and have a 3-year-old child. "
    "I do not know where to go for affordable health services. "
    "I need help with nutrition, vaccination, and finding a nearby facility."
)

DEMO_PROFILE = {
    "pincode": "560001",
    "pregnant": True,
    "recently_delivered": False,
    "child_under_5": True,
    "child_age_months": 36,
    "nutrition_need": True,
    "uninsured": False,
    "adult_woman": True,
}


# ── _deterministic_questions ────────────────────────────────────────────────

def test_demo_profile_includes_insurance_question():
    """Demo profile (pincode known, no insurance keyword in text) → asks insurance."""
    from src.followup import _deterministic_questions
    questions = _deterministic_questions(DEMO_PROFILE, DEMO_TEXT)
    ids = [q["id"] for q in questions]
    assert "insurance" in ids, f"Expected insurance question, got ids: {ids}"


def test_demo_profile_includes_travel_and_urgency():
    """Demo profile → also asks travel distance and urgency."""
    from src.followup import _deterministic_questions
    questions = _deterministic_questions(DEMO_PROFILE, DEMO_TEXT)
    ids = [q["id"] for q in questions]
    assert "travel_distance" in ids, f"Expected travel_distance, got: {ids}"
    assert "urgency" in ids, f"Expected urgency, got: {ids}"


def test_demo_profile_returns_exactly_3():
    """Demo profile → exactly 3 follow-up questions."""
    from src.followup import _deterministic_questions
    questions = _deterministic_questions(DEMO_PROFILE, DEMO_TEXT)
    assert len(questions) == 3, f"Expected 3 questions, got {len(questions)}: {questions}"


def test_no_pincode_first_question_is_pincode():
    """No pincode in profile → first question asks for it."""
    from src.followup import _deterministic_questions
    profile = {"pregnant": True, "adult_woman": True}
    questions = _deterministic_questions(profile, "I am pregnant and need help.")
    assert len(questions) >= 1
    assert questions[0]["id"] == "pincode"
    assert questions[0]["type"] == "text"


def test_no_pincode_max_3_questions():
    """Even without pincode, no more than 3 questions returned."""
    from src.followup import _deterministic_questions
    questions = _deterministic_questions({})
    assert len(questions) <= 3


def test_insurance_in_text_skips_insurance_question():
    """When insurance is explicitly mentioned, skip the insurance question."""
    from src.followup import _deterministic_questions
    profile = {"pincode": "560001"}
    raw = "I am uninsured and need help with maternal care in pincode 560001."
    questions = _deterministic_questions(profile, raw)
    ids = [q["id"] for q in questions]
    assert "insurance" not in ids, f"Expected no insurance question when uninsured in text; got: {ids}"


def test_all_questions_have_required_fields():
    """Every question dict must have id, question, type, and options."""
    from src.followup import _deterministic_questions
    for q in _deterministic_questions(DEMO_PROFILE, DEMO_TEXT):
        assert "id" in q, f"Missing 'id' in {q}"
        assert "question" in q, f"Missing 'question' in {q}"
        assert "type" in q, f"Missing 'type' in {q}"
        assert "options" in q, f"Missing 'options' in {q}"
        assert isinstance(q["options"], list)


def test_radio_questions_have_options():
    """Radio-type questions must have at least 2 options."""
    from src.followup import _deterministic_questions
    for q in _deterministic_questions(DEMO_PROFILE, DEMO_TEXT):
        if q["type"] == "radio":
            assert len(q["options"]) >= 2, f"Radio question {q['id']} has <2 options"


# ── generate_followup_questions (no API) ────────────────────────────────────

def test_generate_followup_no_api_falls_back_to_deterministic():
    """Without an API key, generate_followup_questions returns deterministic questions."""
    import src.followup as fmod
    original = fmod.CLAUDE_AVAILABLE
    fmod.CLAUDE_AVAILABLE = False
    try:
        questions = fmod.generate_followup_questions(DEMO_PROFILE, DEMO_TEXT)
        assert 2 <= len(questions) <= 3
        ids = [q["id"] for q in questions]
        assert "insurance" in ids
    finally:
        fmod.CLAUDE_AVAILABLE = original


def test_generate_followup_count_in_range():
    """Result always has 2-3 questions."""
    import src.followup as fmod
    original = fmod.CLAUDE_AVAILABLE
    fmod.CLAUDE_AVAILABLE = False
    try:
        questions = fmod.generate_followup_questions({}, "No info provided")
        assert 2 <= len(questions) <= 3
    finally:
        fmod.CLAUDE_AVAILABLE = original


# ── apply_followup_answers ──────────────────────────────────────────────────

def _ins_q():
    return [{"id": "insurance", "type": "radio",
             "options": ["Yes, I have insurance", "No, I don't have insurance", "Not sure"],
             "question": "Do you have insurance?"}]


def _urg_q():
    return [{"id": "urgency", "type": "radio",
             "options": ["Urgent — I need help today", "Routine — planning ahead"],
             "question": "Is this urgent?"}]


def _travel_q():
    return [{"id": "travel_distance", "type": "radio",
             "options": ["Up to 5 km", "Up to 10 km", "Up to 25 km"],
             "question": "How far can you travel?"}]


def test_apply_no_insurance_sets_uninsured_true():
    from src.followup import apply_followup_answers
    updated = apply_followup_answers({}, _ins_q(), {"insurance": "No, I don't have insurance"})
    assert updated["uninsured"] is True


def test_apply_yes_insurance_sets_uninsured_false():
    from src.followup import apply_followup_answers
    updated = apply_followup_answers({"uninsured": True}, _ins_q(), {"insurance": "Yes, I have insurance"})
    assert updated["uninsured"] is False


def test_apply_not_sure_insurance_leaves_profile_unchanged():
    from src.followup import apply_followup_answers
    original_val = False
    updated = apply_followup_answers({"uninsured": original_val}, _ins_q(), {"insurance": "Not sure"})
    assert updated["uninsured"] == original_val


def test_apply_urgency_urgent():
    from src.followup import apply_followup_answers
    updated = apply_followup_answers({}, _urg_q(), {"urgency": "Urgent — I need help today"})
    assert updated.get("urgency") == "urgent"


def test_apply_urgency_routine():
    from src.followup import apply_followup_answers
    updated = apply_followup_answers({}, _urg_q(), {"urgency": "Routine — planning ahead"})
    assert updated.get("urgency") == "routine"


def test_apply_travel_5km():
    from src.followup import apply_followup_answers
    updated = apply_followup_answers({}, _travel_q(), {"travel_distance": "Up to 5 km"})
    assert updated.get("travel_km") == 5


def test_apply_travel_10km():
    from src.followup import apply_followup_answers
    updated = apply_followup_answers({}, _travel_q(), {"travel_distance": "Up to 10 km"})
    assert updated.get("travel_km") == 10


def test_apply_travel_25km():
    from src.followup import apply_followup_answers
    updated = apply_followup_answers({}, _travel_q(), {"travel_distance": "Up to 25 km"})
    assert updated.get("travel_km") == 25


def test_apply_does_not_mutate_original():
    """apply_followup_answers must return a copy, never mutate the input."""
    from src.followup import apply_followup_answers
    original = {"uninsured": None}
    apply_followup_answers(original, _ins_q(), {"insurance": "No, I don't have insurance"})
    assert original["uninsured"] is None


def test_apply_empty_answers_leaves_profile_unchanged():
    from src.followup import apply_followup_answers
    profile = {"pregnant": True, "uninsured": False}
    updated = apply_followup_answers(profile, _ins_q() + _urg_q(), {})
    assert updated["pregnant"] is True
    assert updated["uninsured"] is False
    assert "urgency" not in updated


def test_apply_complete_demo_followup():
    """All three demo questions answered → profile enriched correctly."""
    from src.followup import apply_followup_answers
    questions = _ins_q() + _travel_q() + _urg_q()
    answers = {
        "insurance": "No, I don't have insurance",
        "travel_distance": "Up to 10 km",
        "urgency": "Routine — planning ahead",
    }
    updated = apply_followup_answers(DEMO_PROFILE.copy(), questions, answers)
    assert updated["uninsured"] is True
    assert updated["travel_km"] == 10
    assert updated["urgency"] == "routine"
    # Original profile fields preserved
    assert updated["pregnant"] is True
    assert updated["pincode"] == "560001"
