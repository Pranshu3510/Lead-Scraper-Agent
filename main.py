"""
Lead Extraction Agent — Main Orchestrator
==========================================
Autonomous loop that discovers B2B leads via Perplexity sonar-pro,
deduplicates against a local SQLite database, and stores net-new profiles
until a configurable daily quota is reached.

Usage:
    python main.py                     # Full run (200 leads)
    python main.py --quota 10          # Test run with 10 leads
    python main.py --dry-run           # Simulate without API calls
    python main.py --export-only       # Just export today's leads to CSV
"""

import argparse
import json
import os
import sys
import time
from datetime import date

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import box

import db
import search
from utils import build_email, rotate_search_params, extract_domain, verify_email_deliverability


# Force UTF-8 on Windows to avoid cp1252 encoding errors
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(force_terminal=True)

# ---------------------------------------------------------------------------
# Dry-run mock data
# ---------------------------------------------------------------------------

MOCK_COMPANIES = [
    {"company_name": "AlphaLedger", "domain": "alphaledger.io", "industry": "Fintech", "location": "NYC",
     "description": "Blockchain-based accounting platform for enterprises"},
    {"company_name": "LexiFlow", "domain": "lexiflow.com", "industry": "Legal Tech", "location": "London",
     "description": "AI-powered contract analysis and management"},
    {"company_name": "SteelBridge MFG", "domain": "steelbridgemfg.com", "industry": "Industrial Manufacturing",
     "location": "Mumbai", "description": "Precision steel components for automotive"},
]

MOCK_EXECUTIVES = [
    {"first_name": "Sarah", "last_name": "Chen", "title": "CEO",
     "linkedin": "https://linkedin.com/in/sarahchen", "opportunity": "Decision maker for digital transformation"},
    {"first_name": "Raj", "last_name": "Patel", "title": "CTO",
     "linkedin": "https://linkedin.com/in/rajpatel", "opportunity": "Oversees technology modernization initiatives"},
]


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------

def run_agent(config: dict, dry_run: bool = False, quota_override: int = None):
    """
    Core agent loop:
    1. Pick industry/location combo
    2. Search Perplexity for companies
    3. For each company: check dedup → find executives → deduce email → store
    4. Repeat until quota is met
    """
    quota = quota_override or config["daily_quota"]
    model = config["groq_model"]
    delay = config.get("request_delay_seconds", 1.5)
    industries = config["target_industries"]
    locations = config["target_locations"]
    titles = config["target_titles"]
    size_min = config["company_size_min"]
    size_max = config["company_size_max"]

    # Initialize database
    db.init_db()

    # Check how many we already have today (for resume support)
    existing_today = db.get_session_count()
    session_leads = existing_today

    console.print(Panel(
        f"[bold cyan]J. Lambert Foundry — Lead Extraction Agent[/bold cyan]\n\n"
        f"  Target:     {quota} leads\n"
        f"  Existing:   {existing_today} (today)\n"
        f"  Remaining:  {max(0, quota - session_leads)}\n"
        f"  Industries: {', '.join(industries)}\n"
        f"  Locations:  {', '.join(locations)}\n"
        f"  Mode:       {'[DRY RUN]' if dry_run else '[LIVE]'}",
        title="Agent Initialized",
        border_style="bright_blue",
        box=box.DOUBLE,
    ))

    if session_leads >= quota:
        console.print(f"\n[green]✓ Daily quota already met ({session_leads}/{quota}).[/green]")
        return

    iteration = 0
    consecutive_empty = 0
    max_empty_iterations = len(industries) * len(locations) * 2  # safety valve

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Extracting leads...", total=quota, completed=session_leads
        )

        while session_leads < quota:
            # Rotate through industry/location combos
            industry, location = rotate_search_params(industries, locations, iteration)
            iteration += 1

            progress.update(task, description=f"[cyan]{industry}[/cyan] in [yellow]{location}[/yellow]")

            # ----------------------------------------------------------
            # Step 1: Search for companies
            # ----------------------------------------------------------
            console.print(f"\n[bold]── Iteration {iteration} ──[/bold]  "
                          f"[cyan]{industry}[/cyan] × [yellow]{location}[/yellow]")

            if dry_run:
                companies_raw = MOCK_COMPANIES[:3]
                console.print(f"  [dim](dry-run: using {len(companies_raw)} mock companies)[/dim]")
            else:
                known_domains = db.get_all_domains()
                companies_raw = search.search_companies(
                    industry=industry,
                    location=location,
                    size_min=size_min,
                    size_max=size_max,
                    model=model,
                    known_domains=known_domains,
                    delay=delay,
                )

            if not companies_raw:
                console.print(f"  [yellow]⚠ No companies found, trying next combo...[/yellow]")
                consecutive_empty += 1
                if consecutive_empty >= max_empty_iterations:
                    console.print(f"  [red]✗ Too many empty iterations ({consecutive_empty}). Stopping.[/red]")
                    break
                continue

            consecutive_empty = 0
            console.print(f"  [green]→ Found {len(companies_raw)} companies[/green]")

            # ----------------------------------------------------------
            # Step 2–4: For each company, dedup → enrich → store
            # ----------------------------------------------------------
            for comp in companies_raw:
                if session_leads >= quota:
                    break

                comp_name = comp.get("company_name", "Unknown")
                comp_domain = extract_domain(comp.get("domain", ""))
                comp_industry = comp.get("industry", industry)
                comp_location = comp.get("location", location)

                if not comp_domain:
                    console.print(f"    [dim]SKIP (no domain): {comp_name}[/dim]")
                    continue

                # Dedup check: domain
                if db.domain_exists(comp_domain):
                    console.print(f"    [dim]SKIP (domain exists): {comp_domain}[/dim]")
                    continue

                console.print(f"    [white]>> {comp_name}[/white] ({comp_domain})")

                # Find executives
                if dry_run:
                    execs_raw = MOCK_EXECUTIVES[:2]
                else:
                    known_names = db.get_all_names()
                    execs_raw = search.search_executives(
                        company_name=comp_name,
                        domain=comp_domain,
                        target_titles=titles,
                        model=model,
                        known_names=known_names,
                        delay=delay,
                    )

                if not execs_raw:
                    console.print(f"      [dim]No executives found[/dim]")
                    continue

                # Deduce email format
                if dry_run:
                    email_format = "first.last"
                else:
                    email_format = search.deduce_email_format(
                        domain=comp_domain,
                        company_name=comp_name,
                        model=model,
                        delay=delay,
                    )

                console.print(f"      Email format: [magenta]{email_format}@{comp_domain}[/magenta]")

                # Insert company
                company_id = db.insert_company(
                    domain=comp_domain,
                    name=comp_name,
                    industry=comp_industry,
                    location=comp_location,
                    email_format=email_format,
                )

                # Process each executive
                for ex in execs_raw:
                    if session_leads >= quota:
                        break

                    first = ex.get("first_name", "").strip()
                    last = ex.get("last_name", "").strip()
                    title = ex.get("title", "").strip()
                    linkedin = ex.get("linkedin", "")
                    opportunity = ex.get("opportunity", "")

                    if not first or not last or not title:
                        continue

                    # Build email
                    email = build_email(first, last, email_format, comp_domain)
                    if not email:
                        continue

                    # Dedup check: email
                    if db.email_exists(email):
                        console.print(f"      [dim]SKIP (email exists): {email}[/dim]")
                        continue

                    # Deliverability check
                    if not dry_run and not verify_email_deliverability(email):
                        console.print(f"      [yellow]SKIP (invalid or no MX record): {email}[/yellow]")
                        continue

                    # Dedup check: person at this company
                    if db.person_exists(first, last, comp_domain):
                        console.print(f"      [dim]SKIP (person exists): {first} {last}[/dim]")
                        continue

                    # Store the lead
                    lead_id = db.insert_lead(
                        company_id=company_id,
                        first_name=first,
                        last_name=last,
                        title=title,
                        email=email,
                        linkedin=linkedin,
                        systemic_opportunity=opportunity,
                        location=comp_location,
                        industry=comp_industry,
                    )

                    if lead_id:
                        session_leads += 1
                        progress.update(task, completed=session_leads)
                        console.print(
                            f"      [green][OK] [{session_leads}/{quota}][/green] "
                            f"{first} {last} - {title} - {email}"
                        )

                        # Print the lead as JSON for logging
                        lead_json = {
                            "FirstName": first,
                            "LastName": last,
                            "Title": title,
                            "Company": comp_name,
                            "Email": email,
                            "Systemic_Opportunity": opportunity,
                        }
                        console.print(f"        [dim]{json.dumps(lead_json)}[/dim]")

    # ----------------------------------------------------------
    # Step 5: Export & Summary
    # ----------------------------------------------------------
    today = date.today().isoformat()
    export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
    export_path = os.path.join(export_dir, f"leads_{today}.csv")

    total_exported = db.export_csv(export_path)

    # Summary table
    console.print()
    summary = Table(title="Session Summary", box=box.ROUNDED, border_style="bright_green")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", style="cyan")
    summary.add_row("Total leads today", str(db.get_session_count()))
    summary.add_row("Target quota", str(quota))
    summary.add_row("Iterations run", str(iteration))
    summary.add_row("CSV export", export_path)
    summary.add_row("Rows exported", str(total_exported))
    console.print(summary)

    if session_leads >= quota:
        console.print(f"\n[bold green]Daily quota of {quota} leads reached![/bold green]")
    else:
        console.print(f"\n[yellow]⚠ Session ended with {session_leads}/{quota} leads.[/yellow]")


# ---------------------------------------------------------------------------
# Export-only mode
# ---------------------------------------------------------------------------

def export_only():
    """Export today's leads to CSV without running the agent."""
    db.init_db()
    today = date.today().isoformat()
    export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
    export_path = os.path.join(export_dir, f"leads_{today}.csv")
    count = db.export_csv(export_path)
    console.print(f"[green]✓ Exported {count} leads to {export_path}[/green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="J. Lambert Foundry — Autonomous Lead Extraction Agent"
    )
    parser.add_argument(
        "--quota", type=int, default=None,
        help="Override the daily quota (default: from config.json)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run with mock data — no API calls"
    )
    parser.add_argument(
        "--export-only", action="store_true",
        help="Just export today's leads to CSV"
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config.json (default: ./config.json)"
    )
    args = parser.parse_args()

    # Load config
    config_path = args.config or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.json"
    )
    if not os.path.exists(config_path):
        console.print(f"[red]✗ Config not found: {config_path}[/red]")
        sys.exit(1)

    with open(config_path, "r") as f:
        config = json.load(f)

    if args.export_only:
        export_only()
        return

    run_agent(
        config=config,
        dry_run=args.dry_run,
        quota_override=args.quota,
    )


if __name__ == "__main__":
    main()
