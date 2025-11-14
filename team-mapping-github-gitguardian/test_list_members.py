#!/usr/bin/env python3
"""
Test script to run list_all_gg_members() function.
Make sure you have the required environment variables set:
- GITGUARDIAN_TOKEN (required)
- GITGUARDIAN_INSTANCE (optional, defaults to https://api.gitguardian.com)
"""

import logging
import sys
from gitguardian_calls import list_all_gg_members

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Test the list_all_gg_members() function."""
    try:
        logger.info("Starting to fetch all GitGuardian members...")
        
        member_count = 0
        max_members_to_print = 5  # Limit output for debugging
        
        for member in list_all_gg_members():
            member_count += 1
            
            # Only print first few members to reduce output noise
            if member_count <= max_members_to_print:
                # Print member details
                print(f"\nMember #{member_count}:")
                print(f"  ID: {member.id}")
                print(f"  Email: {member.email}")
                print(f"  Name: {getattr(member, 'name', 'N/A')}")
                print(f"  Role: {getattr(member, 'role', 'N/A')}")
                # Print other attributes if they exist
                if hasattr(member, '__dict__'):
                    for key, value in member.__dict__.items():
                        if key not in ['id', 'email', 'name', 'role']:
                            print(f"  {key}: {value}")
            elif member_count == max_members_to_print + 1:
                print(f"\n... (suppressing further member details, showing count only)")
        
        logger.info(f"\nTotal members fetched: {member_count}")
        
    except RuntimeError as e:
        logger.error(f"Error occurred: {e}")
        sys.exit(1)
    except KeyError as e:
        logger.error(f"Missing required environment variable: {e}")
        logger.error("Please set GITGUARDIAN_TOKEN environment variable")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

