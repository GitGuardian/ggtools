# Script to Map Severities to Risk Scores

To learn more on [GitGuardian risk score](https://docs.gitguardian.com/releases/saas/2025/12/17/2-changelog)


## Severity Mapping (editable)

```bash
SEVERITY_MAPPING = {
    "critical": 80,  # Risk score >= 80
    "high": 60,      # Risk score >= 60 and < 80
    "medium": 40,    # Risk score >= 40 and < 60
    "low": 20,       # Risk score >= 20 and < 40
    "info": 0,       # Risk score < 20
}
```
[GitGuardian_API_KEY creation](https://docs.gitguardian.com/api-docs/personal-access-tokens) use SATs for higher rate-limits.

```bash

cd risk-to-severity-mapping/
python3 -mvenv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Required: Your GitGuardian API key
export GITGUARDIAN_API_KEY="your_api_key_here"

# Optional: API URL (defaults to US region)
export GITGUARDIAN_API_URL="https://api.gitguardian.com"
# For EU region, use: https://api.eu1.gitguardian.com

# Optional: Test mode without making changes
export DRY_RUN="true"

# Test run without making changes
DRY_RUN=true python3 sync_risk_to_severity.py

# Live run
python3 sync_risk_to_severity.py
```

## Output and Summary

```bash
Incident 22404169: Risk Score=20 | Current=info → Target=low
Incident 23139880: Risk Score=86 | Current=info → Target=critical

No more pages - pagination complete

================================================================================
EXECUTION SUMMARY
================================================================================
Total incidents processed: 2325
Incidents updated:         1773
Incidents skipped:         552
Errors:                    0
================================================================================
```
