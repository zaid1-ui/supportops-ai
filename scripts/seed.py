"""Seed users, tickets, and knowledge for local development.

Usage:  python -m scripts.seed                # users + the 3 named sample tickets
        python -m scripts.seed --count 50     # users + 50 procedurally generated tickets
        python -m scripts.seed --count 100 --force
        python -m scripts.seed --create TK-5005 --subject "..." --body "..." [--customer customer@example.com] [--tier enterprise] [--sla 4]

--count N     seeds N tickets in total (the 3 named ones plus generated ones to
              reach N). Rerunning the script is idempotent: tickets whose id
              already exists are left untouched.
--force       also delete pre-existing generated tickets before seeding, so the
              count is exact. Use it to reset the queue to a known size.
--create ID   add one custom ticket with the given id (e.g. TK-5005) so you can
              run a workflow against a ticket you invent on the spot. Needs
              --subject and --body. Skips if the id already exists.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from backend.app.api.auth import ensure_user
from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Role, Ticket, TicketStatus

# example.com is the RFC 2606 reserved documentation domain. Not .local — that
# is reserved for mDNS by RFC 6762, and EmailStr rejects it, so seeded users
# would exist in the database but be unable to log in.
SEED_USERS = [
    ("agent@example.com", "agent123", "Tier-1 Agent", Role.AGENT),
    ("engineer@example.com", "engineer123", "Tier-2 Engineer", Role.ENGINEER),
    ("lead@example.com", "lead123", "Support Lead", Role.LEAD),
    ("admin@example.com", "admin123", "Platform Admin", Role.ADMIN),
]

# The three named tickets double as documentation and as stable fixtures the
# evaluation harness and the docs refer to by id. Keep them; add more with
# --count or by appending to this list.
SEED_TICKETS = [
    Ticket(
        id="TK-1001",
        subject="CSV export never completes",
        body=(
            "I'm trying to export about 80,000 rows and the job just spins. "
            "I've left it running for an hour twice now. Nothing in my email either."
        ),
        customer_email="dana@acme.example",
        account_tier="enterprise",
        status=TicketStatus.OPEN,
        sla_hours=8,
        message_count=3,
    ),
    Ticket(
        id="TK-1002",
        subject="Refund for duplicate charge",
        body="I was billed twice for the same invoice this month. Please refund the duplicate ($640).",
        customer_email="omar@globex.example",
        account_tier="standard",
        status=TicketStatus.OPEN,
        sla_hours=24,
    ),
    Ticket(
        id="TK-1003",
        subject="Everything is down!!!",
        body="Cannot log in. Neither can anyone on my team. This is unacceptable.",
        customer_email="priya@initech.example",
        account_tier="enterprise",
        status=TicketStatus.OPEN,
        sla_hours=2,
        reopen_count=1,
    ),
]

# --- Procedural ticket generator -----------------------------------------
# Realistic-but-synthetic subjects and bodies so --count N produces tickets a
# triage agent can actually classify (varied intent, severity, product area,
# SLA). The customer email is RFC 2606-safe (.example).

_SUBJECTS = [
    "Login page returns 500 on submit",
    "Invoice line items missing from export",
    "Two-factor code never arrives",
    "Integration webhook stopped firing",
    "Dashboard chart shows stale data",
    "My API key was revoked without notice",
    "Cannot attach files larger than 10MB",
    "SSO session expires too quickly",
    "Report scheduling is an hour off",
    "Billing address cannot be updated",
    "Search returns no results for my docs",
    "Rate limit hit on a paid plan",
    "Export CSV has comma problems",
    "Password reset link is invalid",
    "Team member cannot access shared folder",
    "Webhook signature mismatch",
    "Mobile app crashes on login",
    "Duplicate rows in the report",
    "Audit log missing entries",
    "Custom field max length too short",
]

_BODIES = [
    "Whenever I hit the submit button the page errors out. Has been doing this since the latest release.",
    "I generated a report and the amounts add up to less than expected. Comparing to last month the same report was correct.",
    "I requested a code but nothing arrives in my inbox or spam. I need access urgently.",
    "Our CRM stopped receiving events about an hour ago and nothing has come through since.",
    "The metrics on the overview dashboard are not updating even though the underlying data has changed.",
    "I did not revoke this key myself. Please check who did and restore my access.",
    "The upload fails and the error message just says the file is too large even though it is under the limit.",
    "Users are being logged out after a few minutes of inactivity. It should be at least an hour.",
    "The scheduled report runs an hour later than the time I set. Timezone handling looks off.",
    "I cannot change my billing address on file. The save button does nothing.",
    "Searching for recent documents returns nothing even though they exist. Indexing seems broken.",
    "My plan includes a generous rate limit but I am hitting it constantly after the last change.",
    "Exporting data with commas in the fields splits them into wrong columns in Excel.",
    "The reset link emailed to me says it is expired even though I clicked it minutes after requesting it.",
    "One of my team members cannot open the shared folder we gave them access to.",
    "The webhook signatures stopped validating on our side. The secret looks unchanged.",
    "The app closes immediately when I try to log in from my phone.",
    "The same record appears twice in the generated report every time I run it.",
    "Some events are missing from the audit log for the past two days.",
    "The custom field has a character limit that is too low for the data we need to store.",
]


def _gen_ticket(index: int) -> Ticket:
    rng = random.Random(index)  # deterministic per index: same id -> same ticket
    idx = rng.randrange(len(_SUBJECTS))
    tier = rng.choice(["standard", "enterprise", "growth"])
    status = rng.choices(
        [TicketStatus.OPEN, TicketStatus.PENDING_CUSTOMER],
        weights=[0.85, 0.15],
        k=1,
    )[0]
    return Ticket(
        id=f"TK-{2000 + index:04d}",
        subject=_SUBJECTS[idx],
        body=_BODIES[idx],
        customer_email=f"customer{index}@example.com",
        account_tier=tier,
        status=status,
        sla_hours=rng.choice([2, 4, 8, 24, 48]),
        reopen_count=rng.choices([0, 0, 0, 1, 2], weights=[6, 6, 6, 1, 1], k=1)[0],
        message_count=rng.randint(1, 6),
    )


def generate_tickets(total: int) -> list[Ticket]:
    """Return exactly `total` tickets: the named ones first, then generated.

    Generated ids are TK-2001, TK-2002, ... so they never collide with the
    TK-100x named fixtures. Deterministic per id, so re-seeding with the same
    count rebuilds the same queue.
    """
    tickets = list(SEED_TICKETS)
    needed = total - len(tickets)
    if needed > 0:
        tickets += [_gen_ticket(i) for i in range(1, needed + 1)]
    return tickets[:total]


def _create_custom_ticket(db, args) -> int:
    """Add one custom ticket (e.g. TK-5005). Returns 1 if created, 0 if already present."""
    if db.get(Ticket, args.create) is not None:
        print(f"tickets: {args.create} already exists — left untouched")
        return 0
    customer = args.customer or f"customer{args.create}@example.com"
    db.add(
        Ticket(
            id=args.create,
            subject=args.subject,
            body=args.body,
            customer_email=customer,
            account_tier=args.tier,
            status=TicketStatus.OPEN,
            sla_hours=args.sla,
            message_count=1,
        )
    )
    db.commit()
    print(f"tickets: created {args.create} — '{args.subject}' (customer {customer}, tier {args.tier}, SLA {args.sla}h)")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed SupportOps demo data.")
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Total tickets to seed (default: the 3 named fixtures).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete pre-existing generated tickets first so the count is exact.",
    )
    parser.add_argument(
        "--create",
        metavar="ID",
        default=None,
        help="Add one custom ticket with this id (e.g. TK-5005).",
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="Subject for --create.",
    )
    parser.add_argument(
        "--body",
        default=None,
        help="Body text for --create.",
    )
    parser.add_argument(
        "--customer",
        default=None,
        help="Customer email for --create (default: customer{id}@example.com).",
    )
    parser.add_argument(
        "--tier",
        default="standard",
        help="Account tier for --create (standard/enterprise/growth).",
    )
    parser.add_argument(
        "--sla",
        type=int,
        default=24,
        help="SLA hours for --create (default: 24).",
    )
    args = parser.parse_args(argv)

    if args.create:
        if not (args.subject and args.body):
            parser.error("--create ID requires --subject and --body")
        if args.count:
            parser.error("--create and --count are mutually exclusive")

    init_db()
    db = SessionLocal()
    try:
        for email, pw, name, role in SEED_USERS:
            ensure_user(db, email, pw, name, role)
        print(f"users:   {len(SEED_USERS)} — e.g. lead@example.com / lead123")

        if args.create:
            _create_custom_ticket(db, args)
        else:
            if args.force:
                # Only the generated range (TK-2001..) is farmed out; the named
                # fixtures are kept so the docs/eval references stay valid.
                deleted = (
                    db.query(Ticket)
                    .filter(Ticket.id.like("TK-2%"))
                    .delete(synchronize_session=False)
                )
                db.commit()
                print(f"tickets: removed {deleted} previously generated tickets (--force)")

            tickets = generate_tickets(args.count) if args.count else SEED_TICKETS
            created = 0
            for t in tickets:
                if db.get(Ticket, t.id) is None:
                    db.add(t)
                    created += 1
            db.commit()
            print(f"tickets: {created} created, {len(tickets) - created} already present (total {len(tickets)})")

        kb = Path("data/knowledge")
        if kb.exists() and any(kb.iterdir()):
            print("knowledge: found docs in data/knowledge — upload them via POST /documents/upload")
        else:
            print("knowledge: none — upload via POST /documents/upload")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
