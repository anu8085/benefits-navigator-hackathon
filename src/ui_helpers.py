from __future__ import annotations
import json
from typing import Any


def safe_nfhs_value(v: Any) -> tuple[str, str]:
    """Return (display_str, quality) — quality in {'certain','uncertain','suppressed','missing'}."""
    if v is None:
        return ("N/A", "missing")
    s = str(v).strip()
    if s in ("", "NA", "nan", "None"):
        return ("N/A", "missing")
    if s == "*":
        return ("* (suppressed)", "suppressed")
    if s.startswith("(") and s.endswith(")"):
        return (f"{s} (uncertain)", "uncertain")
    try:
        float(s)
        return (s, "certain")
    except ValueError:
        return (s, "uncertain")


def safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).strip()
        if s in ("", "NA", "na", "nan", "None"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def format_facility(f: dict) -> dict:
    """Return a display-ready dict for a facility row."""
    phone = f.get("officialPhone") or ""
    if not phone:
        raw_phones = f.get("phone_numbers", "")
        if raw_phones and raw_phones.startswith("["):
            try:
                phones = json.loads(raw_phones)
                if phones:
                    phone = str(phones[0])
            except Exception:
                pass

    return {
        "name": f.get("name", "Unnamed facility"),
        "type": f.get("organization_type", ""),
        "address": ", ".join(
            x for x in [
                f.get("address_line1", ""),
                f.get("address_city", ""),
                f.get("address_stateOrRegion", ""),
                f.get("address_zipOrPostcode", ""),
            ] if x
        ),
        "phone": phone,
        "email": f.get("email", ""),
        "specialties": f.get("specialties", ""),
        "lat": safe_float(f.get("latitude")),
        "lon": safe_float(f.get("longitude")),
    }


# Curated subset of NFHS indicators shown in the UI
_NFHS_KEY_LABELS: dict[str, str] = {
    "institutional_birth_5y_pct": "Institutional births (%)",
    "mothers_who_had_at_least_4_anc_visits_lb5y_pct": "4+ ANC visits (%)",
    "mothers_who_consumed_ifa_for_100_days_or_more_when_they_wer_pct": "IFA 100+ days (%)",
    "child_12_23m_fully_vaccinated_based_on_information_from_eit_pct": "Children fully vaccinated (%)",
    "child_u5_who_are_stunted_height_for_age_18_pct": "Child stunting (%)",
    "child_u5_who_are_underweight_weight_for_age_18_pct": "Child underweight (%)",
    "prev_diarrhoea_2wk_child_u5_pct": "Child diarrhea prevalence (%)",
    "hh_member_covered_health_insurance_pct": "Health insurance coverage (%)",
    "hh_improved_water_pct": "Improved water source (%)",
    "hh_use_improved_sanitation_pct": "Improved sanitation (%)",
    "non_pregnant_w15_49_who_are_anaemic_lt_12_0_g_dl_22_pct": "Women anaemia (%)",
    "pregnant_w15_49_who_are_anaemic_lt_11_0_g_dl_22_pct": "Pregnant women anaemia (%)",
    "women_age_30_49_years_ever_undergone_a_cervical_screen_pct": "Cervical screening (%)",
    "w20_24_married_before_age_18_years_pct": "Child marriage (women 20-24, %)",
    "child_u6m_exclusively_breastfed_pct": "Exclusive breastfeeding <6m (%)",
}


def get_nfhs_display_rows(nfhs_row: dict) -> list[dict]:
    """Return curated NFHS indicators as a list of {label, value, quality, key} dicts."""
    result = []
    for key, label in _NFHS_KEY_LABELS.items():
        v = nfhs_row.get(key)
        display, quality = safe_nfhs_value(v)
        result.append({"label": label, "value": display, "quality": quality, "key": key})
    return result
