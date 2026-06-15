"""BENEFITBRIDGE AI — Gate A local-only Streamlit app.

Runs entirely on local sample JSON files + SQLite.
No live Databricks / Unity Catalog / Lakebase connections in this gate.
Claude API is used if ANTHROPIC_API_KEY is set; falls back to deterministic otherwise.
"""
from __future__ import annotations

import json

import streamlit as st

from src.config import CLAUDE_AVAILABLE, CLAUDE_MODEL, SAMPLE_DATA_DIR
from src.data_loader import (
    _load,
    _norm,
    get_district_alias,
    get_district_for_pincode,
    get_facilities,
    get_nfhs_for_district,
    list_nfhs_districts,
    load_pathways,
    load_scenarios,
)
from src.profile_extractor import extract_profile
from src.rules_engine import _eval_condition, match_pathways
from src.action_plan import generate_action_plan
from src.state_store import StateStore
from src.ui_helpers import format_facility, get_nfhs_display_rows

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BenefitBridge AI",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session state init ───────────────────────────────────────────────────────
_STATE_DEFAULTS: dict = {
    "step": 0,
    "raw_text": "",
    "profile": None,
    "matched_pathways": [],
    "action_plan": "",
    "plan_method": "",
    "nfhs_rows": [],
    "facilities_list": [],
    "district_info": {},
}
for _k, _v in _STATE_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

store = StateStore()
pathways = load_pathways()

# ── Header ───────────────────────────────────────────────────────────────────
st.title("🌉 BenefitBridge AI")
mode_label = f"Claude AI ({CLAUDE_MODEL})" if CLAUDE_AVAILABLE else "Deterministic (no API key)"
st.caption(
    "Connecting families to health benefits in India · "
    f"AI mode: **{mode_label}** · "
    f"Data: local sample JSON (Gate A)"
)

tab1, tab2, tab3 = st.tabs(
    ["👪 Family Navigator", "📊 Program Leader Dashboard", "🔍 Data Trust / Debug"]
)

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — FAMILY NAVIGATOR
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    step = st.session_state.step

    # ── STEP 0: Free-text input ─────────────────────────────────────────────
    if step == 0:
        st.subheader("Tell us about your family")

        scenarios = load_scenarios()
        if scenarios:
            st.write("**Quick-start demo scenarios:**")
            demo_cols = st.columns(min(len(scenarios), 3))
            for i, sc in enumerate(scenarios):
                if demo_cols[i % 3].button(sc["title"][:55], key=f"demo_{i}"):
                    st.session_state.raw_text = sc["scenario_text"]
                    st.rerun()

        st.markdown("---")
        raw = st.text_area(
            "Describe your family's situation and health needs:",
            value=st.session_state.raw_text,
            height=130,
            placeholder=(
                "Example: I live in pincode 560001. I am pregnant and have a 3-year-old child. "
                "I need help with nutrition and finding a nearby health facility."
            ),
        )

        if st.button("Analyse My Family Profile", type="primary", disabled=not raw.strip()):
            spinner_msg = "Extracting profile with Claude…" if CLAUDE_AVAILABLE else "Extracting profile…"
            with st.spinner(spinner_msg):
                profile = extract_profile(raw.strip())

            pincode = profile.get("pincode") or ""
            district_info: dict = {}
            nfhs_rows: list[dict] = []
            facilities: list[dict] = []

            if pincode:
                district_info = get_district_for_pincode(pincode) or {}
                if district_info:
                    profile["district_norm"] = district_info["district_norm"]
                    profile["state_norm"] = district_info["state_norm"]
                    nfhs_rows = get_nfhs_for_district(
                        district_info["district_norm"], district_info["state_norm"]
                    )
                    facilities = get_facilities(
                        pincode, district_info["district_norm"], district_info["state_norm"]
                    )

            st.session_state.raw_text = raw.strip()
            st.session_state.profile = profile
            st.session_state.district_info = district_info
            st.session_state.nfhs_rows = nfhs_rows
            st.session_state.facilities_list = facilities
            st.session_state.step = 1
            st.rerun()

    # ── STEP 1: Profile review / edit ───────────────────────────────────────
    elif step == 1:
        profile: dict = st.session_state.profile

        st.subheader("Confirm Your Family Profile")
        method = profile.get("extraction_method", "unknown")
        st.caption(
            f"Profile extracted via **{method}**. "
            "Tick or untick boxes to correct anything before we find pathways."
        )

        with st.expander("Original text", expanded=False):
            st.write(st.session_state.raw_text)

        c1, c2 = st.columns(2)
        with c1:
            profile["pincode"] = st.text_input("Pincode", value=profile.get("pincode") or "")
            profile["pregnant"] = st.checkbox("Pregnant", value=bool(profile.get("pregnant")))
            profile["recently_delivered"] = st.checkbox(
                "Recently delivered", value=bool(profile.get("recently_delivered"))
            )
            profile["adult_woman"] = st.checkbox(
                "Adult woman", value=bool(profile.get("adult_woman"))
            )
            profile["child_under_5"] = st.checkbox(
                "Child under 5 years", value=bool(profile.get("child_under_5"))
            )
            if profile["child_under_5"]:
                age_val = st.number_input(
                    "Child age (months)",
                    min_value=0,
                    max_value=59,
                    value=int(profile.get("child_age_months") or 0),
                    step=1,
                )
                profile["child_age_months"] = int(age_val)
            else:
                profile["child_age_months"] = None

        with c2:
            profile["nutrition_need"] = st.checkbox(
                "Nutrition need", value=bool(profile.get("nutrition_need"))
            )
            profile["uninsured"] = st.checkbox(
                "Uninsured / no health coverage", value=bool(profile.get("uninsured"))
            )
            profile["low_income"] = st.checkbox(
                "Low income / BPL", value=bool(profile.get("low_income"))
            )
            profile["water_sanitation_need"] = st.checkbox(
                "Water / sanitation need", value=bool(profile.get("water_sanitation_need"))
            )
            profile["child_diarrhea_risk"] = st.checkbox(
                "Child diarrhea risk", value=bool(profile.get("child_diarrhea_risk"))
            )
            profile["screening_need"] = st.checkbox(
                "Preventive screening need", value=bool(profile.get("screening_need"))
            )

        st.session_state.profile = profile

        col_back, col_next = st.columns([1, 2])
        with col_back:
            if st.button("← Back"):
                st.session_state.step = 0
                st.rerun()
        with col_next:
            if st.button("Find Support Pathways →", type="primary"):
                matched = match_pathways(profile, pathways)

                spin_msg = (
                    "Generating action plan with Claude…"
                    if CLAUDE_AVAILABLE
                    else "Generating action plan…"
                )
                with st.spinner(spin_msg):
                    plan_text, plan_method = generate_action_plan(
                        profile,
                        matched,
                        st.session_state.nfhs_rows,
                        st.session_state.facilities_list,
                    )

                d = st.session_state.district_info
                store.save_session(
                    raw_text=st.session_state.raw_text,
                    profile=profile,
                    plan_text=plan_text,
                    plan_method=plan_method,
                    district_norm=d.get("district_norm", ""),
                    state_norm=d.get("state_norm", ""),
                )

                st.session_state.matched_pathways = matched
                st.session_state.action_plan = plan_text
                st.session_state.plan_method = plan_method
                st.session_state.step = 2
                st.rerun()

    # ── STEP 2: Results ─────────────────────────────────────────────────────
    elif step == 2:
        profile = st.session_state.profile
        matched = st.session_state.matched_pathways
        plan_text = st.session_state.action_plan
        nfhs_rows = st.session_state.nfhs_rows
        facilities = st.session_state.facilities_list
        district_info = st.session_state.district_info

        pin = profile.get("pincode", "?")
        district = district_info.get("district_norm", "")
        state = district_info.get("state_norm", "")
        location_str = f"PIN {pin}" + (f" — {district}, {state}" if district else "")
        st.subheader(f"Results for {location_str}")

        # Matched pathways
        if matched:
            st.write(f"**{len(matched)} support pathway(s) matched your profile:**")
            for pw in matched:
                with st.expander(f"✅ {pw.get('pathway_name', pw.get('pathway_id'))}"):
                    st.write(pw.get("recommended_action", ""))
                    st.caption(
                        f"Category: {pw.get('category', '')}  ·  "
                        f"Trigger: `{pw.get('trigger_condition', '')}`"
                    )
        else:
            st.info(
                "No support pathways matched the current profile. "
                "Please tick additional needs in the previous step, or consult a local health worker."
            )

        # Action plan
        st.markdown("---")
        method_label = "Claude AI" if st.session_state.plan_method == "claude" else "Deterministic rules"
        st.subheader(f"Action Plan  ·  {method_label}")
        st.markdown(plan_text)

        # NFHS district indicators
        if nfhs_rows:
            st.markdown("---")
            row = nfhs_rows[0]
            d_name = row.get("district_name", "").strip() or district
            match_type = "district match" if len(nfhs_rows) == 1 else "state-level context"
            st.subheader(f"District Health Indicators — {d_name} ({match_type}, NFHS-5)")

            indicators = get_nfhs_display_rows(row)
            certain = [i for i in indicators if i["quality"] == "certain"]
            uncertain = [i for i in indicators if i["quality"] in ("uncertain", "suppressed")]

            if certain:
                cols = st.columns(3)
                for idx, ind in enumerate(certain[:12]):
                    with cols[idx % 3]:
                        st.metric(label=ind["label"], value=ind["value"])

            if uncertain:
                with st.expander("Indicators with data quality caveats"):
                    for ind in uncertain:
                        st.write(f"**{ind['label']}**: {ind['value']}")

        # Nearby facilities
        if facilities:
            st.markdown("---")
            st.subheader("Nearby Health Facilities")
            for f in facilities[:5]:
                fd = format_facility(f)
                header = f"🏥 {fd['name']}"
                if fd["address"]:
                    header += f"  ·  {fd['address'][:60]}"
                with st.expander(header):
                    if fd["phone"]:
                        st.write(f"📞 {fd['phone']}")
                    if fd["email"]:
                        st.write(f"📧 {fd['email']}")
                    if fd["specialties"]:
                        st.write(f"Specialties: {fd['specialties']}")
                    if fd["lat"] and fd["lon"]:
                        st.caption(f"Coordinates: {fd['lat']:.4f}, {fd['lon']:.4f}")

        st.markdown("---")
        if st.button("← Start a New Query"):
            for key in list(_STATE_DEFAULTS.keys()):
                st.session_state[key] = _STATE_DEFAULTS[key]
            st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — PROGRAM LEADER DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Program Leader Dashboard")
    st.caption("District health trends · pathway demand simulation · facility overview")

    all_nfhs = _load("nfhs_5_district_health_indicators")

    if not all_nfhs:
        st.warning(
            "No NFHS data loaded. "
            "Run `python scripts/export_sample_data.py` to populate sample_data/."
        )
    else:
        district_names = list_nfhs_districts()
        if not district_names:
            st.warning("No district names found in NFHS data.")
        else:
            selected_district = st.selectbox("Select district:", district_names)
            sel_row = next(
                (r for r in all_nfhs if r.get("district_name", "").strip() == selected_district),
                None,
            )

            if sel_row:
                st.write(f"**{selected_district}** — {sel_row.get('state_ut','').strip()}")

                indicators = get_nfhs_display_rows(sel_row)
                certain = [i for i in indicators if i["quality"] == "certain"]

                if certain:
                    st.markdown("#### Key Health Indicators")
                    metric_cols = st.columns(4)
                    for idx, ind in enumerate(certain[:8]):
                        with metric_cols[idx % 4]:
                            st.metric(ind["label"], ind["value"])
                else:
                    st.info("No numeric indicators available for this district.")

                # Pathway demand simulation against sample scenarios
                st.markdown("---")
                st.markdown("#### Pathway Demand — Sample Scenario Simulation")
                st.caption("Based on 3 included demo scenarios (not real population data)")

                scenarios = load_scenarios()
                demand: dict[str, int] = {pw["pathway_id"]: 0 for pw in pathways}
                for sc in scenarios:
                    signals = sc.get("expected_signals", {})
                    for pw in pathways:
                        if _eval_condition(pw.get("trigger_condition", ""), signals):
                            demand[pw["pathway_id"]] += 1

                for pw in pathways:
                    name = pw.get("pathway_name", pw["pathway_id"])
                    count = demand[pw["pathway_id"]]
                    bar = "█" * count + "░" * (len(scenarios) - count)
                    st.write(f"**{name}**: {bar} {count}/{len(scenarios)}")

        # Facility coverage overview
        st.markdown("---")
        st.markdown("#### Facility Coverage (sample_data)")
        all_facilities = _load("facilities")
        if all_facilities:
            total = len(all_facilities)
            with_phone = sum(1 for f in all_facilities if f.get("officialPhone"))
            with_coords = sum(
                1 for f in all_facilities
                if f.get("latitude") and str(f.get("latitude")).strip() not in ("NA", "")
            )
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("Total facilities", total)
            fc2.metric("With phone number", with_phone)
            fc3.metric("With coordinates", with_coords)
        else:
            st.info("No facilities data loaded.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — DATA TRUST / DEBUG PANEL
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Data Trust / Debug Panel")

    # Source file status
    st.markdown("#### Sample Data Sources")
    source_files = [
        "facilities",
        "india_post_pincode_directory",
        "pincode_district_lookup",
        "nfhs_5_district_health_indicators",
        "support_pathways",
        "sample_scenarios",
    ]
    status_cols = st.columns(3)
    for idx, name in enumerate(source_files):
        rows = _load(name)
        with status_cols[idx % 3]:
            if rows:
                st.success(f"{name}  ({len(rows)} rows)")
            else:
                st.error(f"{name}  MISSING")

    # AI mode
    st.markdown("---")
    st.markdown("#### AI Configuration")
    if CLAUDE_AVAILABLE:
        st.success(f"Claude AI active — model: `{CLAUDE_MODEL}`")
    else:
        st.warning(
            "Deterministic mode — `ANTHROPIC_API_KEY` not set. "
            "Copy `.env.example` to `.env` and add your key to enable Claude."
        )

    # District matching trace
    st.markdown("---")
    st.markdown("#### District Matching Trace")
    test_pin = st.text_input("Enter a pincode to trace:", value="560001", key="debug_pin")
    if test_pin.strip():
        di = get_district_for_pincode(test_pin.strip())
        if di:
            alias = get_district_alias(di["district_norm"])
            st.write(
                f"Lookup → `district_norm={di['district_norm']}`, "
                f"`state_norm={di['state_norm']}`, "
                f"lat={di['lat']}, lon={di['lon']}"
            )
            st.write(f"NFHS alias: `{di['district_norm']}` → `{alias}`")
            nfhs = get_nfhs_for_district(di["district_norm"], di["state_norm"])
            if nfhs:
                match_label = "district match" if _norm(nfhs[0].get("district_name")) == alias else "state fallback"
                st.success(
                    f"NFHS: {len(nfhs)} row(s) found ({match_label}) — "
                    f"district_name=`{nfhs[0].get('district_name','').strip()}`"
                )
            else:
                st.error("No NFHS rows found for this pincode's district/state.")
        else:
            st.error(f"Pincode `{test_pin.strip()}` not found in local sample data.")

    # Recent sessions
    st.markdown("---")
    st.markdown("#### Recent Sessions (SQLite)")
    sessions = store.get_recent_sessions(10)
    if sessions:
        for s in sessions:
            pin_info = f"{s.get('district_norm','')} / {s.get('state_norm','')}"
            st.write(
                f"`{s['id'][:8]}…`  {s['created_at']}  "
                f"— {pin_info}  "
                f"— plan: **{s.get('plan_method','?')}**"
            )
    else:
        st.write("No sessions recorded yet. Complete a Family Navigator query to create one.")

    # Raw data preview
    st.markdown("---")
    st.markdown("#### Sample Data Preview")
    preview_choice = st.selectbox("File to preview:", source_files, key="debug_file")
    preview_rows = _load(preview_choice)
    if preview_rows:
        import pandas as pd

        df = pd.DataFrame(preview_rows[:10])
        st.dataframe(df, use_container_width=True)
        if len(preview_rows) > 10:
            st.caption(f"Showing 10 of {len(preview_rows)} rows.")
    else:
        st.warning(f"No data for `{preview_choice}`.")
