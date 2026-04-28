"""
Data models for the Lead Extraction Agent.
Defines the schema for leads as required by J. Lambert Foundry.
"""

from pydantic import BaseModel, Field
from typing import Optional


class CompanyInfo(BaseModel):
    """Represents a discovered company."""
    name: str
    domain: str
    industry: str = ""
    location: str = ""
    employee_count: Optional[int] = None
    email_format: str = ""  # e.g. "first.last", "firstlast", "f.last"


class ExecutiveInfo(BaseModel):
    """Represents a discovered executive at a company."""
    first_name: str
    last_name: str
    title: str
    linkedin: str = ""


class Lead(BaseModel):
    """
    Final lead schema — matches the JSON output format
    required by J. Lambert Foundry.
    """
    FirstName: str
    LastName: str
    Title: str
    Company: str
    Email: str
    Systemic_Opportunity: str = Field(
        default="",
        description="Why this lead is a high-value opportunity"
    )
    Domain: str = ""
    LinkedIn: str = ""
    Location: str = ""
    Industry: str = ""
