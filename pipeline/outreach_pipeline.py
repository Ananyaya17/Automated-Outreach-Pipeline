from typing import List, Dict, Optional

from models.company import Company
from models.contact import Contact
from services.ocean_client import OceanClient
from services.prospeo_client import ProspeoClient
from services.brevo_client import BrevoClient
from services.email_generator import generate_email
from config.settings import Settings
from utils.logger import get_logger
from rich.console import Console
from rich.table import Table
from pathlib import Path
import csv
import time
import asyncio
from services.async_clients import AsyncOceanClient, AsyncProspeoClient, AsyncBrevoClient

logger = get_logger(__name__)
console = Console()


class OutreachPipeline:
    def __init__(self, settings: Settings, ocean=None, prospeo=None, brevo=None):
        """Initialize the pipeline with optional client instances for testing.
        
        Args:
            settings: Configuration object.
            ocean: Optional OceanClient instance (default: constructed from settings).
            prospeo: Optional ProspeoClient instance (default: constructed from settings).
            brevo: Optional BrevoClient instance (default: constructed from settings).
        """
        self.settings = settings
        self.ocean = ocean or OceanClient(settings.OCEAN_BASE_URL, settings.OCEAN_API_TOKEN, name="ocean")
        self.prospeo = prospeo or ProspeoClient(settings.PROSPEO_BASE_URL, settings.PROSPEO_API_KEY, name="prospeo")
        self.brevo = brevo or BrevoClient(settings.BREVO_BASE_URL, settings.BREVO_API_KEY, name="brevo")
        self.metrics = {
            "start_time": None,
            "companies_found": 0,
            "contacts_found": 0,
            "emails_resolved": 0,
            "emails_sent": 0,
            "failed": 0,
        }

    def run_interactive(self, dry_run: bool = False):
        seed = console.input("Enter seed company domain: ").strip()
        self.run(seed, dry_run=dry_run)

    def _extract_email(self, email_field):
        """Normalize various email field shapes into a plain string or None.

        Handles:
        - dict with key 'email' or 'emailAddress'
        - list of strings
        - plain string
        """
        if not email_field:
            return None
        if isinstance(email_field, dict):
            for key in ("email", "emailAddress", "value"):
                val = email_field.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            return None
        if isinstance(email_field, list):
            for it in email_field:
                if isinstance(it, str) and it.strip():
                    return it.strip()
            return None
        if isinstance(email_field, str):
            return email_field.strip() or None
        return None

    def run(self, seed_domain: str, dry_run: bool = False, limit: int = 10, export_csv: bool = True):
        self.metrics["start_time"] = time.time()
        console.rule("Stage 1: Find similar companies")
        companies = self.ocean.find_similar(seed_domain, limit=limit)
        self.metrics["companies_found"] = len(companies)
        console.print(f"Found {len(companies)} similar companies")
        logger.info("Stage 1: Found %s similar companies for seed %s", len(companies), seed_domain)
        if companies:
            logger.debug("Stage 1 companies: %s", [c.domain for c in companies])

        console.rule("Stage 2: Find decision makers")
        contacts: List[Contact] = []
        per_domain_counts = {}
        # Process domains sequentially to avoid Prospeo rate limits.
        for c in companies:
            try:
                res = self.prospeo.find_contacts(c.domain)
                if not isinstance(res, list):
                    logger.warning("Prospeo returned unexpected result for %s: %s", c.domain, type(res).__name__)
                    self.metrics["failed"] += 1
                    continue
                res = res or []
                per_domain_counts[c.domain] = len(res)
                contacts.extend(res)
                valid_emails = len([contact for contact in res if contact.email])
                console.print(f"[{c.domain}] -> {len(res)} contacts, {valid_emails} with email")
            except Exception as e:
                logger.error("Prospeo error for %s: %s", c.domain, e)
                self.metrics["failed"] += 1
            # Respect rate limits by waiting between domain requests
            time.sleep(2)

        self.metrics["contacts_found"] = len(contacts)
        console.print(f"Stage 2: Completed {len(companies)} API calls, returned {len(contacts)} contacts")
        logger.info("Stage 2: Completed %s API calls, returned %s contacts", len(companies), len(contacts))

        # Sanity check: if all domains returned zero contacts, warn the operator
        if companies and len(contacts) == 0:
            console.print("[bold yellow]Warning:[/bold yellow] Stage 2 is returning empty results. Check API plan or payload format.")
            logger.warning("Stage 2 returned no contacts for any domain: %s", list(per_domain_counts.keys()))

        console.rule("Stage 3: Filter contacts with email")
        leads = [contact for contact in contacts if self._extract_email(contact.email)]
        self.metrics["emails_resolved"] = len(leads)
        console.print(f"Stage 3: Filtered leads count = {len(leads)}")
        logger.info("Stage 3: Leads after email filter = %s", len(leads))

        # Deduplicate by email
        unique = {}
        for c in leads:
            e = self._extract_email(c.email)
            if not e:
                continue
            unique[e.lower()] = c
        leads = list(unique.values())

        console.rule("Stage 4: Safety checkpoint")
        table = Table(title="Summary")
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Total Companies", str(self.metrics["companies_found"]))
        table.add_row("Total Contacts", str(self.metrics["contacts_found"]))
        table.add_row("Total Emails", str(len(leads)))
        console.print(table)

        proceed = True
        if not leads:
            console.print("No valid leads found, skipping email send and CSV export.")
            console.rule("Summary")
            console.print(f"Emails sent: 0, failed: 0")
            console.print(f"Total failures: {self.metrics['failed']}")
            total_time = time.time() - self.metrics["start_time"]
            console.print(f"Execution time: {total_time:.2f}s")
            logger.info("Pipeline finished: %s", self.metrics)
            return

        if not dry_run:
            resp = console.input("Proceed with sending emails? (y/n): ").strip().lower()
            proceed = resp == "y"

        if not proceed:
            console.print("Exiting without sending emails.")
            return

        console.rule("Stage 5: Send emails (Brevo)")
        successes = 0
        failed = 0
        for lead in leads:
            template = generate_email(lead, lead.company_domain)
            ok = False
            if dry_run:
                console.print(f"[dry-run] Would send to user@***.***")
                ok = True
            else:
                ok = self.brevo.send_email(self.settings.BREVO_SENDER_EMAIL, lead.email, template["subject"], template["body"])
            if ok:
                successes += 1
            else:
                failed += 1
                self.metrics["failed"] += 1

        self.metrics["emails_sent"] = successes

        # CSV export
        if export_csv and leads:
            valid_lead_rows = [l for l in leads if l.full_name or l.email]
            if valid_lead_rows:
                outp = Path("exports")
                outp.mkdir(exist_ok=True)
                csv_file = outp / "leads.csv"
                with csv_file.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["company_domain", "contact_name", "title", "linkedin_url", "email"])
                    for l in valid_lead_rows:
                        writer.writerow([l.company_domain, l.full_name, l.title, str(l.linkedin_url) if l.linkedin_url else "", l.email or ""])
                console.print(f"Exported leads to {csv_file}")
            else:
                console.print("No valid lead rows to export, skipping CSV creation.")

        # Summary
        console.rule("Summary")
        console.print(f"Emails sent: {successes}, failed: {failed}")
        console.print(f"Total failures: {self.metrics['failed']}")
        total_time = time.time() - self.metrics["start_time"]
        console.print(f"Execution time: {total_time:.2f}s")
        logger.info("Pipeline finished: %s", self.metrics)

    def run_async_interactive(self, dry_run: bool = False):
        seed = console.input("Enter seed company domain: ").strip()
        asyncio.run(self.run_async(seed, dry_run=dry_run))

    async def run_async(self, seed_domain: str, dry_run: bool = False, limit: int = 10, export_csv: bool = True):
        self.metrics["start_time"] = time.time()
        console.rule("Stage 1 (async): Find similar companies")
        
        async with AsyncOceanClient(self.settings.OCEAN_BASE_URL, self.settings.OCEAN_API_TOKEN) as aocean, \
                   AsyncProspeoClient(self.settings.PROSPEO_BASE_URL, self.settings.PROSPEO_API_KEY) as aprospeo, \
                   AsyncBrevoClient(self.settings.BREVO_BASE_URL, self.settings.BREVO_API_KEY) as abrevo:

            companies = await aocean.find_similar(seed_domain, limit=limit)
            self.metrics["companies_found"] = len(companies)
            console.print(f"Found {len(companies)} similar companies")

            console.rule("Stage 2 (async): Find decision makers")
            contacts = []
            # Call Prospeo sequentially to avoid rate limits; wait between requests
            for c in companies:
                domain = c.domain
                try:
                    res = await aprospeo.find_contacts(domain)
                    if not isinstance(res, list):
                        logger.warning("Async Prospeo returned unexpected result for %s: %s", domain, type(res).__name__)
                        self.metrics["failed"] += 1
                        continue
                    res = res or []
                    contacts.extend(res)
                    valid_emails = len([contact for contact in res if contact.email])
                    console.print(f"[{domain}] -> {len(res)} contacts, {valid_emails} with email")
                except Exception as e:
                    logger.error("Async Prospeo request failed for %s: %s", domain, e)
                    self.metrics["failed"] += 1
                await asyncio.sleep(2)

            self.metrics["contacts_found"] = len(contacts)
            logger.info("Total contacts found across domains: %s", len(contacts))

            console.rule("Stage 3 (async): Filter contacts with email")
            leads = [contact for contact in contacts if self._extract_email(contact.email)]
            self.metrics["emails_resolved"] = len(leads)
            logger.info("Leads with email: %s", len(leads))

            unique = {}
            for c in leads:
                e = self._extract_email(c.email)
                if not e:
                    continue
                unique[e.lower()] = c
            leads = list(unique.values())

            console.rule("Stage 4: Safety checkpoint")
            table = Table(title="Summary")
            table.add_column("Metric")
            table.add_column("Value")
            table.add_row("Total Companies", str(self.metrics["companies_found"]))
            table.add_row("Total Contacts", str(self.metrics["contacts_found"]))
            table.add_row("Total Emails", str(len(leads)))
            console.print(table)

            if not leads:
                console.print("No valid leads found, skipping email send and CSV export.")
                console.rule("Summary")
                console.print(f"Emails sent: 0, failed: 0")
                console.print(f"Total failures: {self.metrics['failed']}")
                total_time = time.time() - self.metrics["start_time"]
                console.print(f"Execution time: {total_time:.2f}s")
                logger.info("Async pipeline finished: %s", self.metrics)
                return

            proceed = True
            if not dry_run:
                resp = console.input("Proceed with sending emails? (y/n): ").strip().lower()
                proceed = resp == "y"

            if not proceed:
                console.print("Exiting without sending emails.")
                return

            console.rule("Stage 5 (async): Send emails (Brevo)")
            tasks = []
            for lead in leads:
                tpl = generate_email(lead, lead.company_domain)
                if dry_run:
                    console.print(f"[dry-run] Would send to user@***.***")
                    continue
                tasks.append(abrevo.send_email(self.settings.BREVO_SENDER_EMAIL, lead.email, tpl["subject"], tpl["body"]))
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                successes = sum(1 for r in results if r is True)
                failed = len(results) - successes
                self.metrics["failed"] += failed
            else:
                successes = len(leads) if dry_run else 0
                failed = 0

            self.metrics["emails_sent"] = successes

            if export_csv and leads:
                valid_lead_rows = [l for l in leads if l.full_name or l.email]
                if valid_lead_rows:
                    outp = Path("exports")
                    outp.mkdir(exist_ok=True)
                    csv_file = outp / "leads.csv"
                    with csv_file.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(["company_domain", "contact_name", "title", "linkedin_url", "email"])
                        for l in valid_lead_rows:
                            writer.writerow([l.company_domain, l.full_name, l.title, str(l.linkedin_url) if l.linkedin_url else "", l.email or ""])
                    console.print(f"Exported leads to {csv_file}")
                else:
                    console.print("No valid lead rows to export, skipping CSV creation.")

            console.rule("Summary")
            console.print(f"Emails sent: {successes}, failed: {failed}")
            console.print(f"Total failures: {self.metrics['failed']}")
            total_time = time.time() - self.metrics["start_time"]
            console.print(f"Execution time: {total_time:.2f}s")
            logger.info("Async pipeline finished: %s", self.metrics)
