#!/usr/bin/env python3
"""
GitGuardian Risk Score to Severity Sync Script
This script fetches incidents, converts risk scores to severity levels,
and updates incidents so they can be properly synced with ArmorCode.

Schedule this script to run daily via cron or your preferred scheduler.
"""

import os
import requests
import time
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# Configuration
API_KEY = os.environ.get("GITGUARDIAN_API_KEY")  # Set this environment variable
API_BASE_URL = os.environ.get("GITGUARDIAN_API_URL", "https://api.gitguardian.com")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

# Risk Score to Severity Mapping
# Adjust these thresholds based on your organization's needs
SEVERITY_MAPPING = {
    "critical": 80,  # Risk score >= 80
    "high": 60,  # Risk score >= 60 and < 80
    "medium": 40,  # Risk score >= 40 and < 60
    "low": 20,  # Risk score >= 20 and < 40
    "info": 0,  # Risk score < 20
}

def get_severity_from_risk_score(risk_score: Optional[int]) -> str:
    """
    Convert a risk score (0-100) to a severity level.

    Args:
        risk_score: Integer between 0-100, or None

    Returns:
        Severity level string (critical, high, medium, low, info, or unknown)
    """
    if risk_score is None:
        return "unknown"

    if risk_score >= SEVERITY_MAPPING["critical"]:
        return "critical"
    elif risk_score >= SEVERITY_MAPPING["high"]:
        return "high"
    elif risk_score >= SEVERITY_MAPPING["medium"]:
        return "medium"
    elif risk_score >= SEVERITY_MAPPING["low"]:
        return "low"
    else:
        return "info"

def get_headers() -> Dict[str, str]:
    """Get API headers with authentication."""
    if not API_KEY:
        raise ValueError("GITGUARDIAN_API_KEY environment variable not set")

    return {
        "Authorization": f"Token {API_KEY}",
        "Content-Type": "application/json"
    }

def fetch_open_incidents(url: Optional[str] = None) -> tuple:
    """
    Fetch open incidents from GitGuardian API.

    Args:
        url: Full URL for paginated request, or None for first page

    Returns:
        Tuple of (response data, next_url)
    """
    if url is None:
        url = f"{API_BASE_URL}/v1/incidents/secrets"
        params = {
            "status": "TRIGGERED",  # Only open incidents
            "per_page": 100,
        }
    else:
        params = None  # URL already contains all parameters

    response = requests.get(
        url,
        headers=get_headers(),
        params=params if params else None
    )
    response.raise_for_status()

    # Get next URL from Link header
    next_url = None
    if "next" in response.links:
        next_url = response.links["next"]["url"]

    return response.json(), next_url

def update_incident_severity(incident_id: int, severity: str) -> bool:
    """
    Update an incident's severity via API.

    Args:
        incident_id: The incident ID to update
        severity: The new severity level

    Returns:
        True if successful, False otherwise
    """
    url = f"{API_BASE_URL}/v1/incidents/secrets/{incident_id}"
    payload = {"severity": severity}

    try:
        response = requests.patch(url, headers=get_headers(), json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error updating incident {incident_id}: {e}")
        return False

def should_update_severity(incident: Dict) -> bool:
    """
    Determine if an incident's severity should be updated.

    Args:
        incident: The incident dictionary from API

    Returns:
        True if severity should be updated
    """
    risk_score = incident.get("risk_score")
    current_severity = incident.get("severity")

    # Skip if no risk score available
    if risk_score is None:
        return False

    # Calculate what the severity should be based on risk score
    target_severity = get_severity_from_risk_score(risk_score)

    # Only update if current severity differs from target
    return current_severity != target_severity

def process_incidents() -> Dict[str, int]:
    """
    Main function to process all open incidents.

    Returns:
        Statistics dictionary with counts
    """
    stats = {
        "total_processed": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }

    print(f"Starting risk score to severity sync - {datetime.now().isoformat()}")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print(f"API Base URL: {API_BASE_URL}")
    print("-" * 80)

    next_url = None
    page_num = 1

    while True:
        print(f"\nFetching page {page_num}...")

        try:
            data, next_url = fetch_open_incidents(next_url)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching incidents: {e}")
            stats["errors"] += 1
            break

        incidents = data if isinstance(data, list) else data.get("results", [])

        if not incidents:
            print("No more incidents to process")
            break

        for incident in incidents:
            incident_id = incident.get("id")
            risk_score = incident.get("risk_score")
            current_severity = incident.get("severity")

            stats["total_processed"] += 1

            if not should_update_severity(incident):
                stats["skipped"] += 1
                continue

            target_severity = get_severity_from_risk_score(risk_score)

            print(f"Incident {incident_id}: "
                  f"Risk Score={risk_score} | "
                  f"Current={current_severity} → Target={target_severity}")

            if not DRY_RUN:
                if update_incident_severity(incident_id, target_severity):
                    stats["updated"] += 1
                    # Rate limiting - be nice to the API
                    time.sleep(0.1)
                else:
                    stats["errors"] += 1
            else:
                stats["updated"] += 1
                print("  [DRY RUN] Would update severity")

        # Check if there's a next page
        if next_url is None:
            print("\nNo more pages - pagination complete")
            break

        page_num += 1

    return stats

def print_summary(stats: Dict[str, int]):
    """Print execution summary."""
    print("\n" + "=" * 80)
    print("EXECUTION SUMMARY")
    print("=" * 80)
    print(f"Total incidents processed: {stats['total_processed']}")
    print(f"Incidents updated:         {stats['updated']}")
    print(f"Incidents skipped:         {stats['skipped']}")
    print(f"Errors:                    {stats['errors']}")
    print("=" * 80)

def main():
    """Main entry point."""
    try:
        stats = process_incidents()
        print_summary(stats)

        # Exit with error code if there were errors
        if stats["errors"] > 0:
            exit(1)

    except KeyboardInterrupt:
        print("\n\nScript interrupted by user")
        exit(130)
    except Exception as e:
        print(f"\nFatal error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
