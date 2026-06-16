# Testing — TrustRoute AI

> **Databricks Apps & Agents for Good Hackathon — Final Submission**  
> TrustRoute AI is an evidence-backed care referral navigator for families, caregivers, community health workers, and field workers.

The app uses:

- Facility data
- India Post PIN code geography
- PIN-to-district lookup
- NFHS-5 district health indicators
- Support pathway rules
- Facility trust scores
- Claude Sonnet
- Unity Catalog trusted tables
- Databricks SQL Warehouse
- Lakebase / Postgres state store
- SQLite local fallback

The app is informational and referral-oriented. It does **not** provide medical diagnosis, legal advice, or final eligibility determination.

---

## 1. Main demo scenario

Use this intake text:

```text
I live in pincode 560001. I am pregnant and have a 3-year-old child.
I do not know where to go for affordable health services.
I need help with nutrition, vaccination, and finding a nearby facility.
```

Recommended follow-up answers:

```text
I currently do not have health insurance and need low-cost care.
Up to 4 km.
It is urgent today, but not an emergency.
```

Expected result:

- PIN `560001` resolves to **BENGALURU URBAN / KARNATAKA**.
- NFHS district context resolves through alias handling to **Bangalore / Karnataka**, or uses state fallback if needed.
- Relevant support pathways appear.
- Maternal Health Support should match.
- Child Nutrition Support should match.
- Child Immunization Support should match.
- Health Insurance / Low-Cost Care Awareness should match when the profile indicates uninsured or affordable-care need.
- Women Preventive Screening may appear as a lower-priority pathway for an adult-woman profile.
- Nearby health facilities appear.
- Facility cards show trust signals and evidence notes.
- Claude Sonnet generates a grounded support plan.
- The plan is cautious and does not invent unsupported benefits, programs, diagnosis, or guaranteed eligibility.
- Save for follow-up persists a facility.
- Feedback save works.
- Data Trust / Debug shows data, AI, and state-store status.

---

## 2. Test gates

Run the gates in order.

| Gate | Data source | State store | Purpose |
|---|---|---|---|
| Gate A | Local sample JSON | SQLite | Prove the app works fully offline/local |
| Gate B | Unity Catalog trusted tables | SQLite | Prove trusted Databricks data works locally |
| Gate C | Unity Catalog trusted tables | Lakebase | Final deployed Databricks App path |

---

## 3. Trusted Unity Catalog source

Current trusted source:

```text
Catalog: benefits_navigator
Schema: trusted
```

Expected Unity Catalog tables:

```text
benefits_navigator.trusted.facilities
benefits_navigator.trusted.india_post_pincode_directory
benefits_navigator.trusted.pincode_district_lookup
benefits_navigator.trusted.nfhs_5_district_health_indicators
benefits_navigator.trusted.support_pathways
benefits_navigator.trusted.facility_trust_scores
```

Expected known row counts for key tables:

```text
facilities: 10088
india_post_pincode_directory: 165627
pincode_district_lookup: 21162
nfhs_5_district_health_indicators: 706
support_pathways: 6
```

`facility_trust_scores` should load if available. If a facility does not match the trust-score table, the app should use proxy evidence scoring from facility record completeness.

---

## 4. Lakebase deployed state store

Final deployed app state uses Lakebase / managed Postgres.

Expected Lakebase resource:

```text
Databricks App: trustroute-ai
Lakebase project: trustroute-ai-lakebase
Lakebase database: databricks_postgres
```

Expected Lakebase app tables:

```text
app_sessions
app_feedback
facility_shortlists
```

These tables should be created automatically by the app or by `scripts/smoke_test_lakebase.py` using `CREATE TABLE IF NOT EXISTS`.

Do **not** manually create these tables unless troubleshooting a deployment issue.

---

## 5. Gate A — Local JSON + SQLite

### Purpose

Gate A proves the app works even if Databricks and Lakebase are unavailable during the demo.

### Start from project base path

```powershell
cd C:\Hackathon\benefits-navigator-hackathon
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Set local environment variables

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

### Validate sample files

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

### Run compile and tests

```powershell
python -m compileall .
python -m pytest tests -q
```

Expected:

```text
All tests pass
```

Latest known result during final development:

```text
351 passed
```

### Launch the app

```powershell
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

### Expected UI badges

```text
Data: Local sample JSON
State: SQLite
AI: Claude Sonnet
```

If the Anthropic key is missing:

```text
AI: Deterministic fallback
```

### Expected Referral Navigator behavior

- TrustRoute AI title appears.
- Scenario input accepts the main demo scenario.
- Follow-up questions appear.
- Profile preview updates insurance, travel range, and urgency.
- Support pathways are matched.
- District health indicators appear.
- Nearby facilities appear.
- Facility cards show trust signals or proxy trust signals.
- Support plan is generated.
- Session saves to SQLite.
- Feedback save works.
- Program Leader Dashboard reflects local saved activity.
- Data Trust / Debug shows local JSON row counts and SQLite state.

### SQLite validation

```powershell
Get-ChildItem .\.local_state\

python -c "import sqlite3; db='.local_state/benefitbridge_local.db'; con=sqlite3.connect(db); print(con.execute('select name from sqlite_master where type="table"').fetchall()); con.close()"
```

Expected:

- `.local_state/benefitbridge_local.db` exists.
- App-state tables exist.
- Recent session appears in Data Trust / Debug after first run.

---

## 6. Gate A fallback test — no Anthropic key

Stop Streamlit with `Ctrl + C`.

Remove the Anthropic key:

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
```

Relaunch:

```powershell
streamlit run app.py
```

Run the same demo scenario.

Expected:

- App does not crash.
- Deterministic fallback support plan appears.
- SQLite save still works.
- Data Trust / Debug shows Anthropic key is missing without exposing secrets.

Restore Anthropic key after fallback test:

```powershell
$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
```

---

## 7. Gate B — Unity Catalog trusted data + SQLite

### Purpose

Gate B proves the app can run locally against trusted Unity Catalog data while still using SQLite for local state.

### Set environment variables

```powershell
$env:DATABRICKS_CONFIG_PROFILE="hackathon-free"
$env:DATABRICKS_HOST="https://dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_SERVER_HOSTNAME="dbc-30b128b6-0c37.cloud.databricks.com"
$env:DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/81c2d8e2b863208b"
$env:DATABRICKS_TOKEN="<your_databricks_token>"

$env:UC_CATALOG="benefits_navigator"
$env:UC_SCHEMA="trusted"
$env:SQL_WAREHOUSE_NAME="Serverless Starter"

$env:ANTHROPIC_API_KEY="<your_anthropic_api_key>"
$env:CLAUDE_MODEL="claude-sonnet-4-5-20250929"

$env:BENEFITBRIDGE_DATA_MODE="uc"
$env:BENEFITS_DATA_MODE="uc"

$env:STATE_STORE_MODE="sqlite"
$env:LOCAL_SQLITE_PATH=".local_state\benefitbridge_local.db"

$env:SHOW_LOCAL_STATE_DEBUG="true"
```

### Validate Unity Catalog access

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

### Run UC smoke test

```powershell
python scripts/smoke_test_uc.py
```

Expected:

```text
Unity Catalog smoke test: success
Support pathways consistency: matches local JSON trigger logic
```

### Launch the app

```powershell
streamlit run app.py
```

Expected UI badges:

```text
Data: Unity Catalog
State: SQLite
AI: Claude Sonnet
```

Expected result:

- Main demo scenario works.
- Data source badge says Unity Catalog.
- State still saves locally to SQLite.
- Facility trust scoring uses Unity Catalog `facility_trust_scores` where matched.
- Facility trust scoring falls back to proxy evidence scoring where not matched.
- Data Trust / Debug shows Unity Catalog row counts.
- No secrets are printed.

---

## 8. Gate C — Databricks App + Unity Catalog + Lakebase

### Purpose

Gate C is the final hackathon submission path.

Expected deployed app:

```text
Databricks App: trustroute-ai
Data: Unity Catalog
State: Lakebase
AI: Claude Sonnet
```

Expected app URL:

```text
https://trustroute-ai-7474651829403388.aws.databricksapps.com
```

### Required Databricks secret scope

```text
Scope: trustroute-ai
```

Expected keys:

```text
anthropic-api-key
databricks-token
lakebase-user
lakebase-password
```

Validate only key metadata:

```powershell
databricks secrets list-secrets trustroute-ai --profile hackathon-free
```

Do not print secret values.

### Expected app resources

```text
lakebase-state
anthropic-api-key
databricks-token
lakebase-user
lakebase-password
```

### Run final checks before deployment

```powershell
python -m compileall .
python -m pytest tests -q
python scripts/smoke_test_uc.py
```

Run Lakebase smoke test if environment variables are available locally:

```powershell
python scripts/smoke_test_lakebase.py
```

A clean skip is acceptable if Lakebase credentials are only injected inside Databricks App runtime.

### Expected deployed UI badges

```text
Data: Unity Catalog
State: Lakebase
AI: Claude Sonnet
```

### Expected deployed behavior

- App opens at Databricks App URL.
- Referral Navigator runs the main demo scenario.
- Claude Sonnet generates the support plan.
- Unity Catalog trusted data loads.
- Nearby Health Facilities appears once.
- Facility trust signals appear.
- Facility evidence includes uncertainty notes.
- Save for follow-up works.
- Feedback save works.
- Lakebase app-state save works.
- Program Leader Dashboard reflects saved activity.
- Data Trust / Debug shows Lakebase connected.
- No secrets appear in UI, logs, screenshots, or repo.

### Lakebase validation examples

Run through the app first:

1. Save one facility for follow-up.
2. Submit feedback.
3. Refresh the app.
4. Confirm saved state still appears or row counts increase.

Expected Data Trust / Debug checks:

```text
State: Lakebase
Lakebase connected: yes
app_sessions row count visible
app_feedback row count visible
facility_shortlists row count visible
```

SQL-style checks, if using a Lakebase SQL client:

```sql
SELECT COUNT(*) AS session_count FROM app_sessions;
SELECT COUNT(*) AS feedback_count FROM app_feedback;
SELECT COUNT(*) AS shortlist_count FROM facility_shortlists;
```

---

## 9. Facility trust scoring test

For any recommended facility, verify the card shows:

- Facility name
- Trust signal
- Score
- Score source
- Why shown
- Contact/location evidence
- Uncertainty note
- Save for follow-up button

Expected wording:

```text
Trust signal reflects available evidence and data completeness — not a guarantee of service quality.
Please call to confirm current services before visiting.
```

Expected source wording:

```text
Score source: Unity Catalog facility trust score table
```

or

```text
Score source: Facility record completeness proxy
```

Do not show raw, user-facing overclaims such as:

```text
best
safest
guaranteed
verified quality
```

---

## 10. Data Trust / Debug test

Open Data Trust / Debug.

Expected:

- Active data mode shown
- Active state mode shown
- Unity Catalog table counts shown
- Lakebase connection status shown in deployed mode
- Claude status shown without printing API key
- Profile lineage shown
- District matching trace shown
- Facility scoring trace shown
- Recent sessions shown
- No secrets printed

---

## 11. Program Leader Dashboard test

Open Program Leader Dashboard.

Expected:

- Facility Coverage uses Unity Catalog trusted data
- Total facilities around `10088`
- Phone coverage metric appears
- Coordinate coverage metric appears
- District health indicators appear
- Pathway demand or sample scenario simulation appears
- Labels do not say old local sample data when running in Unity Catalog mode

---

## 12. What to screenshot for submission/demo

Capture:

1. App title and runtime badges
2. Referral Navigator scenario input
3. Follow-up questions
4. Profile used for routing
5. Matched support pathway cards
6. Claude-generated support plan
7. Nearby facility recommendations with trust signal
8. Facility evidence expander
9. District health indicators
10. Save for follow-up
11. Feedback section
12. Data Trust / Debug row counts
13. Program Leader Dashboard
14. Lakebase status in Data Trust / Debug for Gate C

---

## 13. Pass criteria

The app passes testing when:

- App title is TrustRoute AI.
- Data-source badge is visible and correct.
- State-store badge is visible and correct.
- Main demo scenario works end-to-end.
- District alias handling works for `BENGALURU URBAN` → `Bangalore`.
- Matches come from support pathways only.
- Facilities come from trusted data or approved local sample data only.
- Facility trust signals are visible.
- Action plan avoids unsupported benefit/program claims.
- App does not claim diagnosis or guaranteed eligibility.
- SQLite save works locally.
- Lakebase save works in final deployed mode.
- Feedback save works.
- Save for follow-up works.
- No secret/token/debug leakage appears in UI or logs.
- Deployed Gate C path shows:
  - `Data: Unity Catalog`
  - `State: Lakebase`
  - `AI: Claude Sonnet`

---

## 14. Final demo timing check

Before recording the final 3-minute video, run one clean flow:

```text
Screen 1: paste main scenario
Screen 2: answer follow-up questions
Screen 3: show Claude support plan
Screen 3: show one facility trust card
Screen 3: save one facility for follow-up
Screen 3: show district context
Dashboard: show Program Leader Dashboard
Data Trust: show Unity Catalog + Lakebase status
```

Do not open technical expanders unless needed for judge questions.

---

## 15. Known safe fallback behavior

If Claude is unavailable:

```text
AI: Deterministic fallback
```

Expected:

- App still works
- Support pathways still match
- Facilities still show
- SQLite or Lakebase state still saves
- Debug panel explains fallback without exposing secrets

For final submission, expected state is:

```text
AI: Claude Sonnet
```

If Lakebase is unavailable in local mode:

```text
State: SQLite
```

For final deployed submission, expected state is:

```text
State: Lakebase
```
