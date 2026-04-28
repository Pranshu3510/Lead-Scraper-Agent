"""
Groq API wrapper for the Lead Extraction Agent.
Uses the OpenAI-compatible API at api.groq.com with Llama 3.3 70B.
Free tier: 14,400 requests/day — more than enough for 200 leads.
"""

import os
import json
import time
import re
from typing import Optional
from openai import OpenAI


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------

def get_client() -> OpenAI:
    """Create a Groq client via its OpenAI-compatible endpoint."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY not set. "
            "Run: setx GROQ_API_KEY \"your_key_here\" and restart your terminal."
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[list | dict]:
    """
    Try to extract JSON from the model response.
    Handles cases where the model wraps JSON in markdown code fences.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"\[[\s\S]*\]",
        r"\{[\s\S]*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1) if "```" in pattern else match.group(0))
            except (json.JSONDecodeError, IndexError):
                continue

    return None


def _call_llm(client: OpenAI, model: str, system_prompt: str, user_prompt: str, max_retries: int = 5) -> str:
    """
    Make a Groq API call with automatic retry on rate-limit (429) errors.
    """
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=4096,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate" in error_str.lower():
                wait_time = 30
                retry_match = re.search(r"try again in ([\d.]+)s", error_str, re.IGNORECASE)
                if retry_match:
                    wait_time = int(float(retry_match.group(1))) + 5
                print(f"    [RATE LIMIT] Attempt {attempt + 1}/{max_retries} - waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e

    raise Exception(f"Failed after {max_retries} retries due to rate limiting")


# ---------------------------------------------------------------------------
# Search: Discover companies
# ---------------------------------------------------------------------------

def search_companies(
    industry: str,
    location: str,
    size_min: int,
    size_max: int,
    model: str,
    known_domains: list[str],
    delay: float = 1.5,
) -> list[dict]:
    """
    Ask Groq to find companies matching the target parameters.
    Returns a list of dicts with keys: company_name, domain, industry, location.
    """
    client = get_client()

    exclusion_note = ""
    if known_domains:
        subset = known_domains[-200:]
        exclusion_note = (
            f"\n\nIMPORTANT: Do NOT include any of these companies/domains that we already "
            f"have in our database - skip them entirely:\n{', '.join(subset)}"
        )

    user_prompt = f"""Find exactly 10 real companies in the {industry} industry located in or near {location} 
with approximately {size_min} to {size_max} employees.

For each company, provide:
- company_name: the official name
- domain: their primary website domain (e.g. "example.com", no https://)
- industry: "{industry}"
- location: their city/region
- description: one sentence about what they do

Return ONLY a valid JSON array, no other text. Example format:
[
  {{"company_name": "Acme Corp", "domain": "acmecorp.com", "industry": "Fintech", "location": "NYC", "description": "Digital payments platform for SMBs"}}
]
{exclusion_note}"""

    system_prompt = (
        "You are a B2B market research assistant. You find real, currently operating "
        "companies. Always return valid JSON arrays. Never invent fake companies. "
        "Return ONLY the JSON array, no explanations."
    )

    time.sleep(delay)

    try:
        content = _call_llm(client, model, system_prompt, user_prompt)
        data = _extract_json(content)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"  [ERROR] search_companies failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Search: Find executives at a company
# ---------------------------------------------------------------------------

def search_executives(
    company_name: str,
    domain: str,
    target_titles: list[str],
    model: str,
    known_names: list[str],
    delay: float = 1.5,
) -> list[dict]:
    """
    Ask Groq to find executives at a specific company.
    Returns a list of dicts with keys: first_name, last_name, title, linkedin.
    """
    client = get_client()
    titles_str = ", ".join(target_titles)

    name_exclusion = ""
    if known_names:
        subset = known_names[-100:]
        name_exclusion = (
            f"\n\nDo NOT include these people we already have: {', '.join(subset)}"
        )

    user_prompt = f"""Find the key executives at {company_name} (website: {domain}).

I am specifically looking for people with these titles: {titles_str}.

For each person you find, provide:
- first_name
- last_name
- title: their exact job title
- linkedin: their LinkedIn profile URL if available, otherwise ""
- opportunity: a one-sentence note on why connecting with this person could be valuable for a foundry/manufacturing consultancy

Return ONLY a valid JSON array. Example:
[
  {{"first_name": "Jane", "last_name": "Smith", "title": "CTO", "linkedin": "https://linkedin.com/in/janesmith", "opportunity": "Oversees tech infrastructure modernization"}}
]

If you cannot find any executives matching these titles, return an empty array: []
{name_exclusion}"""

    system_prompt = (
        "You are a B2B executive research assistant. Find real people with real titles. "
        "Never invent or fabricate names. If unsure, return an empty array. "
        "Return ONLY valid JSON, no explanations."
    )

    time.sleep(delay)

    try:
        content = _call_llm(client, model, system_prompt, user_prompt)
        data = _extract_json(content)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"  [ERROR] search_executives failed for {company_name}: {e}")
        return []


# ---------------------------------------------------------------------------
# Search: Deduce email format for a domain
# ---------------------------------------------------------------------------

def deduce_email_format(
    domain: str,
    company_name: str,
    model: str,
    delay: float = 1.5,
) -> str:
    """
    Ask Groq to figure out the corporate email format for a domain.
    Defaults to "first.last" if it can't determine.
    """
    client = get_client()

    user_prompt = f"""What is the corporate email format used by {company_name} ({domain})?

Common patterns:
- first.last (e.g. john.doe@{domain})
- firstlast (e.g. johndoe@{domain})
- f.last (e.g. j.doe@{domain})
- first_last (e.g. john_doe@{domain})
- flast (e.g. jdoe@{domain})
- first (e.g. john@{domain})

Return ONLY a JSON object with one key "format". Example:
{{"format": "first.last"}}

If you cannot determine the format, default to "first.last"."""

    system_prompt = (
        "You are an email intelligence assistant. Determine the corporate "
        "email format for a given company domain. Return ONLY valid JSON, no explanations."
    )

    time.sleep(delay)

    try:
        content = _call_llm(client, model, system_prompt, user_prompt)
        data = _extract_json(content)
        if isinstance(data, dict) and "format" in data:
            return data["format"]
        return "first.last"
    except Exception:
        return "first.last"
