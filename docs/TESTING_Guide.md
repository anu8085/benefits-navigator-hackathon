# Simple Testing Guide — TrustRoute AI

> **Databricks Apps & Agents for Good Hackathon — Final Submission**  
> Use this guide for quick but complete manual testing across all personas: family / field worker, program leader, technical judge, and deployment owner.

TrustRoute AI is an evidence-backed care referral navigator. It uses:

- Unity Catalog trusted data
- Databricks SQL Warehouse
- Claude Sonnet
- deterministic support-pathway matching
- facility trust scoring
- Lakebase state persistence in deployed mode
- SQLite fallback in local mode
- Data Trust / Debug trace for explainability

The app is informational and referral-oriented. It does **not** provide diagnosis, legal advice, final eligibility determination, or guaranteed facility quality.

---

## 1. Personas to test

| Persona | What they test | Success signal |
|---|---|---|
| Family / Caregiver | Plain-language scenario and support plan | Clear next steps, no technical confusion |
| Field Worker / Community Health Worker | Follow-up questions, support pathways, facility cards, save for follow-up | Practical referral workflow works end-to-end |
| Program Leader | Dashboard and aggregate insights | Demand, facility coverage, and district context visible |
| Technical Judge / Reviewer | Data Trust / Debug, evidence, uncertainty, source status | App is grounded, explainable, and does not hide uncertainty |
| Deployment Owner / Admin | Databricks App, Unity Catalog, Lakebase, secrets | Deployed app runs with correct badges and persisted state |

---

## 2. Main winning demo scenario

Paste this into the Referral Navigator:

```text
I live in pincode 560001. I am pregnant and have a 3-year-old child. I do not know where to go for affordable health services. I need help with nutrition, vaccination, and finding a nearby facility.
```

Recommended follow-up answers:

```text
I currently do not have health insurance and need low-cost care.
Up to 4 km.
It is urgent today, but not an emergency.
```

Expected:

- PIN `560001` resolves to **BENGALURU URBAN / KARNATAKA**.
- NFHS context finds **Bangalore / Karnataka** through alias matching.
- Maternal Health Support appears.
- Child Nutrition Support appears.
- Child Immunization Support appears.
- Health Insurance / Low-Cost Care Awareness appears when uninsured / low-cost need is detected.
- Nearby Bengaluru / Karnataka facilities appear.
- Facility trust signal appears.
- Claude Sonnet generates a grounded support plan.
- Save for follow-up works.
- Feedback save works.
- Data Trust / Debug shows source and state-store status.

---

## 3. Expected final deployed badges

For the final hackathon deployment, the app should show:

```text
Data: Unity Catalog
State: Lakebase
AI: Claude Sonnet
```

Local fallback modes may show:

```text
Data: Local sample JSON
State: SQLite
AI: Claude Sonnet
```

or, if the Anthropic key is missing:

```text
AI: Deterministic fallback
```

---

## 4. Test gates

| Gate | Data source | State store | Purpose |
|---|---|---|---|
| Gate A | Local sample JSON | SQLite | Prove the app works fully offline/local |
| Gate B | Unity Catalog trusted tables | SQLite | Prove trusted Databricks data works locally |
| Gate C | Unity Catalog trusted tables | Lakebase | Final deployed Databricks App path |

Run the gates in this order.

---

# Gate A — Local JSON + SQLite

## 5. Gate A purpose

Gate A proves the app works even if Databricks and Lakebase are unavailable.

## 6. Gate A setup

From project base path:

```powershell
cd C:\Hackathon\benefits-navigator-hackathon
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Set environment variables:

```powershell
$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="json_only"
$env:BENEFITS_DATA_MODE="json_only"

$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SAMPLE_DATA_DIR="sample_data"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"
$env:SHOW_LOCAL_STATE_DEBUG="true"
```

Validate sample files:

```powershell
Get-ChildItem .\sample_data\*.json

python -c "import json,glob; [print(f, len(json.load(open(f,encoding='utf-8')))) for f in glob.glob('sample_data/*.json')]"
```

Expected files:

```text
sample_data/facilities.json
sample_data/india_post_pincode_directory.json
sample_data/pincode_district_lookup.json
sample_data/nfhs_5_district_health_indicators.json
sample_data/support_pathways.json
sample_data/sample_scenarios.json
```

Run checks:

```powershell
python -m compileall .
python -m pytest tests -q
```

Latest known full test result:

```text
351 passed
```

Launch:

```powershell
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## 7. Gate A expected UI

Expected badges:

```text
Data: Local sample JSON
State: SQLite
AI: Claude Sonnet
```

Expected Referral Navigator behavior:

- TrustRoute AI title appears.
- Scenario input accepts the main demo scenario.
- Follow-up questions appear.
- Profile preview updates insurance, travel range, and urgency.
- Matched support pathways appear.
- District health indicators appear.
- Nearby health facilities appear.
- Facility trust signal or proxy trust signal appears.
- Claude support plan appears.
- Save for follow-up works.
- Feedback save works.
- Data Trust / Debug shows local JSON row counts.
- Program Leader Dashboard reflects local sample / saved state.

## 8. Gate A SQLite verification

Run:

```powershell
Get-ChildItem .\.local_state\

python -c "import sqlite3; db='.local_state/benefitbridge_local.db'; con=sqlite3.connect(db); print(con.execute('select name from sqlite_master where type="table"').fetchall()); con.close()"
```

Expected:

- `.local_state/benefitbridge_local.db` exists.
- At least one app-state table exists.
- Recent session appears in Data Trust / Debug after the first run.

## 9. Gate A fallback test — no Claude key

Stop the app with `Ctrl + C`.

Remove the key:

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
```

Relaunch:

```powershell
streamlit run app.py
```

Expected:

- App still runs.
- Deterministic fallback plan appears.
- SQLite save still works.
- No secret values are shown.
- Data Trust / Debug clearly shows AI fallback.

Restore key afterward:

```powershell
$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
```

---

# Gate B — Unity Catalog trusted data + SQLite

## 10. Gate B purpose

Gate B proves trusted Databricks data works locally while SQLite handles local state.

## 11. Gate B setup

```powershell
$env:DATABRICKS_CONFIG_PROFILE="hackathon-free"
$env:DATABRICKS_HOST="https://dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_SERVER_HOSTNAME="dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/81c2d8e2b863208b"
$env:DATABRICKS_TOKEN="<your_databricks_token>"

$env:UC_CATALOG="benefits_navigator"
$env:UC_SCHEMA="trusted"

$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="uc"
$env:BENEFITS_DATA_MODE="uc"

$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"
$env:SHOW_LOCAL_STATE_DEBUG="true"
```

Validate Databricks access:

```powershell
databricks current-user me --profile hackathon-free
databricks catalogs list --profile hackathon-free
databricks schemas list benefits_navigator --profile hackathon-free
databricks tables list benefits_navigator trusted --profile hackathon-free
```

Expected tables:

```text
facilities
india_post_pincode_directory
pincode_district_lookup
nfhs_5_district_health_indicators
support_pathways
facility_trust_scores
```

Run smoke test:

```powershell
python scripts/smoke_test_uc.py
```

Expected:

```text
Unity Catalog smoke test: success
Support pathways consistency: matches local JSON trigger logic
```

Launch:

```powershell
streamlit run app.py
```

## 12. Gate B expected UI

Expected badges:

```text
Data: Unity Catalog
State: SQLite
AI: Claude Sonnet
```

Expected:

- Main demo scenario works.
- Unity Catalog row counts appear in Data Trust / Debug.
- Facility scoring uses `facility_trust_scores` where matched.
- Proxy score appears when facility trust score does not match.
- SQLite save still works.
- No local sample label appears when Unity Catalog mode is active.

---

# Gate C — Databricks App + Unity Catalog + Lakebase

## 13. Gate C purpose

Gate C is the final submission path.

Expected deployed app:

```text
Databricks App: trustroute-ai
URL: https://trustroute-ai-7474651829403388.aws.databricksapps.com
Data: Unity Catalog
State: Lakebase
AI: Claude Sonnet
```

## 14. Gate C required secrets

Secret scope:

```text
trustroute-ai
```

Expected keys:

```text
anthropic-api-key
databricks-token
lakebase-user
lakebase-password
```

Verify metadata only:

```powershell
databricks secrets list-secrets trustroute-ai --profile hackathon-free
```

Do not print secret values.

## 15. Gate C required app resources

Expected app resources:

```text
lakebase-state
anthropic-api-key
databricks-token
lakebase-user
lakebase-password
```

Expected Lakebase configuration:

```text
Project: trustroute-ai-lakebase
Database: databricks_postgres
```

Expected Lakebase tables:

```text
app_sessions
app_feedback
facility_shortlists
```

## 16. Gate C pre-deploy checks

Run:

```powershell
python -m compileall .
python -m pytest tests -q
python scripts/smoke_test_uc.py
```

Run if local Lakebase env vars are available:

```powershell
python scripts/smoke_test_lakebase.py
```

A clean skip is acceptable if Lakebase env vars are only injected in Databricks App runtime.

## 17. Gate C deployed validation

Open the deployed app URL.

Expected badges:

```text
Data: Unity Catalog
State: Lakebase
AI: Claude Sonnet
```

Run the main demo scenario.

Expected:

- App opens successfully.
- Referral Navigator works.
- Follow-up questions appear.
- Profile used for routing updates.
- Claude Sonnet support plan appears.
- Nearby Health Facilities appears once.
- Facility trust signals appear.
- Save for follow-up persists.
- Feedback persists.
- Program Leader Dashboard loads.
- Data Trust / Debug shows Lakebase connected.
- No secrets are visible.

## 18. Gate C Lakebase validation

In the app:

1. Run main demo scenario.
2. Save one facility for follow-up.
3. Submit feedback.
4. Refresh the app.
5. Open Data Trust / Debug.

Expected:

```text
State: Lakebase
Lakebase connected: yes
app_sessions row count visible
app_feedback row count visible
facility_shortlists row count visible
```

SQL checks, if using Lakebase SQL client:

```sql
SELECT COUNT(*) AS session_count FROM app_sessions;
SELECT COUNT(*) AS feedback_count FROM app_feedback;
SELECT COUNT(*) AS shortlist_count FROM facility_shortlists;
```

---

# Persona testing

## 19. Persona 1 — Family / Caregiver

### Test goal

Confirm the app feels clear and helpful for a non-technical family user.

### Steps

1. Open Referral Navigator.
2. Paste main demo scenario.
3. Click **Find Trusted Care Options**.
4. Answer follow-up questions.
5. Generate support plan.
6. Read the support plan.
7. Review one facility card.

### Expected

- Language is warm and understandable.
- No SQL, database, or rule syntax is shown in the main flow.
- The plan gives practical next steps.
- The plan says to confirm facility services before visiting.
- No diagnosis or guaranteed eligibility claims appear.

---

## 20. Persona 2 — Field Worker / Community Health Worker

### Test goal

Confirm the workflow supports referral decision-making.

### Steps

1. Run main demo scenario.
2. Answer follow-ups as uninsured / 4 km / urgent today.
3. Review matched support pathways.
4. Review facility trust cards.
5. Open one evidence expander.
6. Save one facility for follow-up.
7. Submit feedback.

### Expected

- Profile used for routing is clear.
- Needs detected are human-readable.
- Pathways explain why they matched.
- Facility card shows trust signal and uncertainty note.
- Save for follow-up works.
- Feedback works.
- No duplicate Nearby Health Facilities section appears.

---

## 21. Persona 3 — Program Leader

### Test goal

Confirm the dashboard provides visibility into demand and coverage.

### Steps

1. Open Program Leader Dashboard.
2. Review pathway demand.
3. Review district health indicators.
4. Review facility coverage metrics.
5. Confirm labels match active data source.
6. Confirm recent/saved activity appears when state is available.

### Expected

- Dashboard says Unity Catalog when in Gate B or Gate C.
- Total facilities is around `10088`.
- Facility coverage and contact completeness metrics appear.
- District health context is visible.
- Saved sessions/feedback contribute to activity where supported.
- No local sample labels appear in deployed mode.

---

## 22. Persona 4 — Technical Judge / Reviewer

### Test goal

Confirm evidence, uncertainty, and technical execution are visible.

### Steps

1. Open Data Trust / Debug.
2. Confirm active data source.
3. Confirm active state store.
4. Confirm Unity Catalog row counts.
5. Confirm Claude status.
6. Confirm Lakebase status in deployed mode.
7. Review district matching trace.
8. Review facility scoring trace.
9. Expand one technical match rule.

### Expected

- Unity Catalog tables are listed.
- Lakebase connection is shown in Gate C.
- No secrets are printed.
- Claude fallback status is transparent.
- Facility trust score source is visible.
- District alias matching is explainable.
- Technical rules are collapsed by default but available.

---

## 23. Persona 5 — Deployment Owner / Admin

### Test goal

Confirm the deployed app is safe, stable, and submission-ready.

### Steps

1. Check app URL opens.
2. Check runtime badges.
3. Check app resources exist.
4. Check secrets exist by metadata only.
5. Run main demo.
6. Save facility.
7. Submit feedback.
8. Refresh.
9. Confirm state persists.
10. Check logs for errors.

### Expected

- Data: Unity Catalog
- State: Lakebase
- AI: Claude Sonnet
- No secrets visible
- App does not crash
- Lakebase persists state
- UC data loads
- Claude action plan works

---

# Scenario set

## 24. Scenario 1 — Main winning demo

```text
I live in pincode 560001. I am pregnant and have a 3-year-old child. I do not know where to go for affordable health services. I need help with nutrition, vaccination, and finding a nearby facility.
```

Expected:

- Maternal Health Support
- Child Nutrition Support
- Child Immunization Support
- Health Insurance / Low-Cost Care Awareness if uninsured need is detected
- Nearby Bengaluru / Karnataka facilities
- Bangalore NFHS context
- Claude support plan

## 25. Scenario 2 — Child nutrition

```text
I live in pincode 560001. I have a 2-year-old child who needs nutrition and growth support. I want to find nearby healthcare help.
```

Expected:

- Child Nutrition Support
- Possibly Child Immunization Support
- Nearby facilities
- District health context

## 26. Scenario 3 — Missing location

```text
I am helping a mother with a young child who needs nutrition and vaccination support.
```

Expected:

- App asks for missing location or PIN code.
- App does not fake nearby facilities.
- App still extracts needs.
- Support plan asks for location before recommending facility routing.

## 27. Scenario 4 — Facility search only

```text
I live near pincode 560001 and need a nearby facility for pregnancy checkups.
```

Expected:

- Maternal Health Support
- Nearby facility recommendations
- Facility trust signal
- No unsupported benefit claims

## 28. Scenario 5 — Control test

```text
I live in pincode 560001. I do not have an urgent health need. I just want to understand what local health resources may exist near me.
```

Expected:

- Fewer urgent pathways
- Safe, general guidance
- No forced eligibility
- No crisis claims

## 29. Scenario 6 — Uninsured / low-cost care

```text
I live in pincode 560001. I need affordable care and do not currently have health insurance.
```

Expected:

- Health Insurance / Low-Cost Care Awareness
- Nearby facility search if requested or inferred
- Safe cost-confirmation language
- No claim that a facility is free unless data supports it

---

# Final submission screenshot checklist

Capture these for README / Devpost / demo support:

1. TrustRoute AI home screen with badges
2. Main scenario input
3. Follow-up questions
4. Profile used for routing
5. Matched support pathways
6. Personalized Support Plan | Claude Sonnet
7. Nearby facility card with trust signal
8. Facility evidence expander
9. Save for follow-up
10. Feedback section
11. District health indicators
12. Program Leader Dashboard
13. Data Trust / Debug with Unity Catalog and Lakebase status

---

# Final pass criteria

The app passes when:

- App title is TrustRoute AI.
- Main scenario works end-to-end.
- Data badge is correct.
- State badge is correct.
- AI badge is correct.
- District alias handling works.
- Support pathways are explainable.
- Facility trust signals are visible.
- Facility evidence includes uncertainty.
- Claude action plan is grounded.
- No unsupported program or benefit is invented.
- No diagnosis or guaranteed eligibility is claimed.
- No duplicate facility section appears.
- SQLite works in local mode.
- Lakebase works in deployed mode.
- Feedback save works.
- Save for follow-up works.
- Data Trust / Debug does not leak secrets.
- Program Leader Dashboard loads.
- Final Gate C app shows:

```text
Data: Unity Catalog
State: Lakebase
AI: Claude Sonnet
```
