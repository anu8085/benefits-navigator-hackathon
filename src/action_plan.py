from __future__ import annotations

from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_AVAILABLE

_PLAN_SYSTEM = """\
You are a health benefits navigator AI for families in India.
Generate a concise, actionable benefit enrollment plan in plain English (max 400 words).
Structure it as numbered steps the family can take TODAY.
Reference the matched support pathways and nearby facilities by name.
Use language simple enough for a community health worker to read aloud.

GROUNDING RULES — follow strictly:
- Use ONLY the support pathways and facility information explicitly provided in this prompt.
- Do NOT name specific government schemes (Ayushman Bharat, ICDS, PM Matru Vandana Yojana,
  Janani Suraksha Yojana, PMMVY, or any other) unless the pathway text below explicitly names them.
- Do NOT promise free food, free medicines, or free services unless the pathway text says so.
- For nutrition needs always say: "Ask the nearest public health facility or local health worker
  about nutrition support options available in your area."
- For health insurance always say: "If you have insurance, confirm whether pregnancy and child care
  are covered. If you do not, ask the facility what public coverage or low-cost options may be available."
- Never assume the family has insurance unless the profile explicitly states uninsured=False.
- When uncertain about a specific service say: "Ask your local health worker or facility."
"""

_NFHS_DISPLAY_COLS = [
    ("institutional_birth_5y_pct", "Institutional births"),
    ("mothers_who_had_at_least_4_anc_visits_lb5y_pct", "4+ ANC visits"),
    ("child_u5_who_are_stunted_height_for_age_18_pct", "Child stunting"),
    ("hh_member_covered_health_insurance_pct", "Health insurance coverage"),
    ("non_pregnant_w15_49_who_are_anaemic_lt_12_0_g_dl_22_pct", "Women anaemia"),
]


def _deterministic_plan(
    profile: dict,
    matched_pathways: list[dict],
    nfhs_rows: list[dict],
    facilities: list[dict],
) -> str:
    if not matched_pathways:
        return (
            "No specific support pathways matched your profile at this time.\n\n"
            "Please speak with a local Anganwadi worker or visit your nearest "
            "Primary Health Centre (PHC) for personalised guidance."
        )

    lines = ["**Your Personalised Action Plan**\n"]
    for i, pw in enumerate(matched_pathways, 1):
        name = pw.get("pathway_name", pw.get("pathway_id", ""))
        action = pw.get("recommended_action", "Visit your nearest health centre.").strip()
        if not action.endswith("."):
            action += "."
        # Bold title on its own line; blank line before recommendation creates
        # a proper markdown paragraph break for readability.
        lines.append(f"**Step {i}: {name}**")
        lines.append("")
        lines.append(action)
        lines.append("")

    if facilities:
        lines.append("---")
        lines.append("**Nearest Health Facilities:**\n")
        for f in facilities[:3]:
            fname = f.get("name", "Unnamed facility")
            city = f.get("address_city", "")
            phone = f.get("officialPhone") or ""
            entry = f"- **{fname}**"
            if city:
                entry += f", {city}"
            if phone:
                entry += f"  ·  {phone}"
            lines.append(entry)

    return "\n".join(lines)


def generate_action_plan(
    profile: dict,
    matched_pathways: list[dict],
    nfhs_rows: list[dict],
    facilities: list[dict],
) -> tuple[str, str]:
    """Return (plan_text, method) — method is 'claude' or 'deterministic'."""
    if CLAUDE_AVAILABLE:
        try:
            import anthropic

            pin = profile.get("pincode", "unknown")
            district = profile.get("district_norm", "")
            state = profile.get("state_norm", "")
            location = f"PIN {pin}"
            if district:
                location += f" ({district}, {state})"

            pathway_lines = "".join(
                f"- {pw.get('pathway_name')}: {pw.get('recommended_action', '')}\n"
                for pw in matched_pathways
            ) or "None matched\n"

            nfhs_lines = ""
            if nfhs_rows:
                r = nfhs_rows[0]
                nfhs_lines = f"District: {r.get('district_name','').strip()}, {r.get('state_ut','').strip()}\n"
                for col, label in _NFHS_DISPLAY_COLS:
                    v = str(r.get(col, "")).strip()
                    if v and v not in ("NA", "*", "nan", ""):
                        nfhs_lines += f"  {label}: {v}%\n"

            fac_lines = "".join(
                f"- {f.get('name','?')}, {f.get('address_city','')} | {f.get('officialPhone','')}\n"
                for f in facilities[:3]
            ) or "No facilities in local dataset\n"

            user_msg = (
                f"Family location: {location}\n"
                f"Profile: pregnant={profile.get('pregnant')}, "
                f"child_under_5={profile.get('child_under_5')}, "
                f"child_age_months={profile.get('child_age_months')}, "
                f"nutrition_need={profile.get('nutrition_need')}, "
                f"uninsured={profile.get('uninsured')}\n\n"
                f"Matched support pathways:\n{pathway_lines}\n"
                f"District health context (NFHS-5):\n{nfhs_lines or 'No data available'}\n"
                f"Nearby facilities:\n{fac_lines}\n"
                "Generate a numbered action plan for this family."
            )

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=900,
                thinking={"type": "adaptive"},
                system=_PLAN_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            plan_text = ""
            for block in response.content:
                if block.type == "text":
                    plan_text += block.text

            if plan_text.strip():
                return plan_text.strip(), "claude"
        except Exception:
            pass

    return _deterministic_plan(profile, matched_pathways, nfhs_rows, facilities), "deterministic"
