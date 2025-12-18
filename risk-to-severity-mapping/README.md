# Script to Map Severities to Risk Scores

To learn more, read about the [GitGuardian risk score](https://docs.gitguardian.com/releases/saas/2025/12/17/2-changelog)

## ‼️ Prerequisites and Assumptions

This application assumes the following:

1. A *nix or bash-like environment for execution (For Windows users we recommend  Git Bash, or WSL)
1. A working, non-eol `python3`, `pip`, and `venv` installation.
1. A GitGuardian SaaS account in good standing - risk scores are not currently supported in On-Prem installs.

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
      "critical": 80,  # Risk score >= 80
      "high": 60,      # Risk score >= 60 and < 80
      "medium": 40,    # Risk score >= 40 and < 60
      "low": 20,       # Risk score >= 20 and < 40
      "info": 0,       # Risk score < 20
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

      # OPTIONAL: Test mode without making changes
      export DRY_RUN="true"

      # Test run without making changes (n.b: we set DRY_RUN inline here)
      DRY_RUN=true python3 sync_risk_to_severity.py

      # Live run
      python3 sync_risk_to_severity.py
      ```

## 👀 Example Output

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
