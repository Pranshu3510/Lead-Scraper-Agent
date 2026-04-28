"""
Database layer for the Lead Extraction Agent.
SQLite-based storage with built-in deduplication via UNIQUE constraints.
"""

import sqlite3
import csv
import os
from datetime import date
from typing import Optional
from models import Lead


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = DB_PATH):
    """Create tables if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            industry TEXT DEFAULT '',
            location TEXT DEFAULT '',
            email_format TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            title TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            linkedin TEXT DEFAULT '',
            systemic_opportunity TEXT DEFAULT '',
            location TEXT DEFAULT '',
            industry TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id)
        );

        CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
        CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
        CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);
    """)
    conn.commit()
    conn.close()


def domain_exists(domain: str, db_path: str = DB_PATH) -> bool:
    """Check if a company domain already exists in the database."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT 1 FROM companies WHERE LOWER(domain) = LOWER(?) LIMIT 1",
        (domain.strip(),)
    ).fetchone()
    conn.close()
    return row is not None


def email_exists(email: str, db_path: str = DB_PATH) -> bool:
    """Check if a lead email already exists in the database."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT 1 FROM leads WHERE LOWER(email) = LOWER(?) LIMIT 1",
        (email.strip(),)
    ).fetchone()
    conn.close()
    return row is not None


def person_exists(first_name: str, last_name: str, domain: str, db_path: str = DB_PATH) -> bool:
    """Check if a person at a specific company already exists."""
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT 1 FROM leads l
           JOIN companies c ON l.company_id = c.id
           WHERE LOWER(l.first_name) = LOWER(?)
             AND LOWER(l.last_name) = LOWER(?)
             AND LOWER(c.domain) = LOWER(?)
           LIMIT 1""",
        (first_name.strip(), last_name.strip(), domain.strip())
    ).fetchone()
    conn.close()
    return row is not None


def insert_company(
    domain: str,
    name: str,
    industry: str = "",
    location: str = "",
    email_format: str = "",
    db_path: str = DB_PATH
) -> int:
    """
    Insert a company, or return existing id if domain already exists.
    Returns the company_id.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO companies (domain, name, industry, location, email_format)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(domain) DO UPDATE SET
                   name = excluded.name,
                   industry = COALESCE(NULLIF(excluded.industry, ''), companies.industry),
                   location = COALESCE(NULLIF(excluded.location, ''), companies.location),
                   email_format = COALESCE(NULLIF(excluded.email_format, ''), companies.email_format)""",
            (domain.strip().lower(), name.strip(), industry, location, email_format)
        )
        conn.commit()
        # Fetch the id (whether inserted or updated)
        row = conn.execute(
            "SELECT id FROM companies WHERE LOWER(domain) = LOWER(?)", (domain.strip(),)
        ).fetchone()
        conn.close()
        return row["id"]
    except Exception as e:
        conn.close()
        raise e


def insert_lead(
    company_id: int,
    first_name: str,
    last_name: str,
    title: str,
    email: str,
    linkedin: str = "",
    systemic_opportunity: str = "",
    location: str = "",
    industry: str = "",
    db_path: str = DB_PATH
) -> Optional[int]:
    """
    Insert a lead. Returns lead_id on success, None if duplicate.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO leads
               (company_id, first_name, last_name, title, email, linkedin,
                systemic_opportunity, location, industry)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id, first_name.strip(), last_name.strip(), title.strip(),
             email.strip().lower(), linkedin, systemic_opportunity, location, industry)
        )
        conn.commit()
        lead_id = cursor.lastrowid
        conn.close()
        return lead_id
    except sqlite3.IntegrityError:
        # Duplicate email
        conn.close()
        return None
    except Exception as e:
        conn.close()
        raise e


def get_session_count(db_path: str = DB_PATH) -> int:
    """Count how many leads were added today."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM leads WHERE date(created_at) = date('now')"
    ).fetchone()
    conn.close()
    return row["cnt"]


def get_all_domains(db_path: str = DB_PATH) -> list[str]:
    """Get all company domains currently in the database."""
    conn = get_connection(db_path)
    rows = conn.execute("SELECT domain FROM companies").fetchall()
    conn.close()
    return [r["domain"] for r in rows]


def get_all_names(db_path: str = DB_PATH) -> list[str]:
    """Get all lead full names currently in the database."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT first_name || ' ' || last_name as full_name FROM leads"
    ).fetchall()
    conn.close()
    return [r["full_name"] for r in rows]


def export_csv(output_path: str, db_path: str = DB_PATH) -> int:
    """
    Export today's leads to a CSV file.
    Returns the number of rows exported.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT
               l.first_name as FirstName,
               l.last_name as LastName,
               l.title as Title,
               c.name as Company,
               l.email as Email,
               l.systemic_opportunity as Systemic_Opportunity,
               c.domain as Domain,
               l.linkedin as LinkedIn,
               l.location as Location,
               l.industry as Industry
           FROM leads l
           JOIN companies c ON l.company_id = c.id
           WHERE date(l.created_at) = date('now')
           ORDER BY l.id"""
    ).fetchall()
    conn.close()

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "FirstName", "LastName", "Title", "Company", "Email",
            "Systemic_Opportunity", "Domain", "LinkedIn", "Location", "Industry"
        ])
        for row in rows:
            writer.writerow([
                row["FirstName"], row["LastName"], row["Title"],
                row["Company"], row["Email"], row["Systemic_Opportunity"],
                row["Domain"], row["LinkedIn"], row["Location"], row["Industry"]
            ])

    return len(rows)
