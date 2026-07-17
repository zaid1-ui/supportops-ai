"""Seed users, tickets, and knowledge for local development.

Usage:  python -m scripts.seed
"""

from __future__ import annotations

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


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        for email, pw, name, role in SEED_USERS:
            ensure_user(db, email, pw, name, role)
        print(f"users:   {len(SEED_USERS)} — e.g. lead@example.com / lead123")

        created = 0
        for t in SEED_TICKETS:
            if db.get(Ticket, t.id) is None:
                db.add(t)
                created += 1
        db.commit()
        print(f"tickets: {created} created, {len(SEED_TICKETS) - created} already present")

        kb = Path("data/knowledge")
        if kb.exists() and any(kb.iterdir()):
            print(f"knowledge: ingest with  python -m scripts.ingest {kb}")
        else:
            print("knowledge: none — upload via POST /documents/upload")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
