"""
Utility functions for the Lead Extraction Agent.
"""

import re
from email_validator import validate_email, EmailNotValidError


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

def verify_email_deliverability(email: str) -> bool:
    """
    Checks if an email is syntactically valid and if its domain has valid MX records,
    indicating it can actually receive emails. This helps prevent bounces.
    """
    try:
        # check_deliverability=True performs DNS lookups to check for MX records
        validate_email(email, check_deliverability=True)
        return True
    except EmailNotValidError:
        return False


# ---------------------------------------------------------------------------
# Email construction
# ---------------------------------------------------------------------------

def build_email(first_name: str, last_name: str, format_pattern: str, domain: str) -> str:
    """
    Build an email address from a name and a format pattern.

    Supported patterns:
        first.last  -> john.doe@domain.com
        firstlast   -> johndoe@domain.com
        f.last      -> j.doe@domain.com
        first_last  -> john_doe@domain.com
        flast       -> jdoe@domain.com
        first       -> john@domain.com
        last.first  -> doe.john@domain.com
    """
    first = sanitize_name(first_name)
    last = sanitize_name(last_name)

    if not first or not last:
        return ""

    pattern = format_pattern.strip().lower()

    builders = {
        "first.last":  f"{first}.{last}",
        "firstlast":   f"{first}{last}",
        "f.last":      f"{first[0]}.{last}",
        "first_last":  f"{first}_{last}",
        "flast":       f"{first[0]}{last}",
        "first":       first,
        "last.first":  f"{last}.{first}",
    }

    local_part = builders.get(pattern, f"{first}.{last}")
    return f"{local_part}@{domain.strip().lower()}"


def sanitize_name(name: str) -> str:
    """Clean a name for email construction — lowercase, alphanumeric only."""
    name = name.strip().lower()
    # Remove non-alpha characters (hyphens, apostrophes, accents, etc.)
    name = re.sub(r"[^a-z]", "", name)
    return name


# ---------------------------------------------------------------------------
# Search parameter rotation
# ---------------------------------------------------------------------------

def rotate_search_params(
    industries: list[str],
    locations: list[str],
    iteration: int,
) -> tuple[str, str]:
    """
    Cycle through all industry × location combinations.
    Each iteration picks a different combo to avoid repeating the same search.
    """
    combos = [(ind, loc) for ind in industries for loc in locations]
    idx = iteration % len(combos)
    return combos[idx]


# ---------------------------------------------------------------------------
# Domain extraction
# ---------------------------------------------------------------------------

def extract_domain(url_or_domain: str) -> str:
    """Extract a clean domain from a URL or domain string."""
    d = url_or_domain.strip().lower()
    # Remove protocol
    d = re.sub(r"^https?://", "", d)
    # Remove www.
    d = re.sub(r"^www\.", "", d)
    # Remove path
    d = d.split("/")[0]
    return d
