# Script to Map Severities to Risk Scores

To learn more, read about the [GitGuardian risk score](https://docs.gitguardian.com/releases/saas/2025/12/17/2-changelog)

## ⚠️ Important: Severity Rules Engine Compatibility

By default, this script **only updates incidents with "unknown" severity**. This design preserves severities that may have been:

- Set manually by users
- Configured via the [Severity Rules Engine](https://docs.gitguardian.com/internal-monitoring/remediate/prioritize-incidents#severity)

If you want to override all severities (including those set by users or the Severity Rules Engine), use the `--force` flag.

## ‼️ Prerequisites and Assumptions

This application assumes the following:

1. A *nix or bash-like environment for execution (For Windows users we recommend  Git Bash, or WSL)
1. A working, non-eol `python3`, `pip`, and `venv` installation.
1. A GitGuardian SaaS account in good standing - risk scores are not currently supported in On-Prem installs.

Please note that only "Open" Incidents will be mapped. Incidents in the `Resolved` or `Ignored` state will be left as-is.

## 🛠️ Installation and Configuration

1. Create a virtual python environment (Optional, Recommended):

      ```bash
      cd risk-to-severity-mapping/ # **this directory**
      python3 -m venv --prompt risk-mapping .venv
      ```

1. Activate environment and install requirements:

      ```bash
      source .venv/bin/activate
      pip install -r requirements.txt
      ```

1. Acquire an API key:

      * Use a Service Access Token (SAT) for higher rate-limits.
      * Set the scope to `Incidents:write, Incidents:read`
      * See the [GitGuardian Documentation](https://docs.gitguardian.com/api-docs/service-accounts) for more info.

1. OPTIONAL: Configure your mapping values in the script:

      Edit lines 26 thru 30 of the script to customize your mapping values

      ```python
      SEVERITY_MAPPING = {
      "critical": 85,  # Risk score >= 85
      "high": 60,      # Risk score >= 60 and < 85
      "medium": 40,    # Risk score >= 40 and < 60
      "low": 26,       # Risk score >= 26 and < 40
      "info": 0,       # Risk score 0-25
      }
      ```

## 🚀 Execution

1. Activate the environment (if not already active) set your variables, and run the script:

      ```bash
      # Activate the environment
      source .venv/bin/activate

      # Set up Your GitGuardian API key in the environment.
      export GITGUARDIAN_API_KEY="your_api_key_here"

      # OPTIONAL: Set the API URL (defaults to US region)
      export GITGUARDIAN_API_URL="https://api.gitguardian.com" # US Region
      # For EU region, use: https://api.eu1.gitguardian.com

      # Test run without making changes (only updates "unknown" severities)
      python3 sync_risk_to_severity.py
      
      # OPTIONAL: Set DRY_RUN to false to enable updating (report only by default)
      export DRY_RUN="false"

      # Live run (n.b: we set DRY_RUN inline here)
      DRY_RUN=false python3 sync_risk_to_severity.py

      # Force update ALL severities (overrides Severity Rules Engine and manual settings)
      DRY_RUN=false python3 sync_risk_to_severity.py --force
      ```

## 👀 Example Output

```bash
Starting risk score to severity sync - 2025-12-18T10:30:00.000000
Mode: DRY RUN
Update mode: UNKNOWN severity only
API Base URL: https://api.gitguardian.com
--------------------------------------------------------------------------------
Incident 22404169: Risk Score=20 | Current=unknown → Target=low
Incident 23139880: Risk Score=86 | Current=unknown → Target=critical

================================================================================
EXECUTION SUMMARY
================================================================================
Total incidents processed: 2325
Incidents updated:         1773
Incidents skipped:         552
Errors:                    0
================================================================================
```
