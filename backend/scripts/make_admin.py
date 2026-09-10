"""Promote an already-registered user to admin, or demote them back to student.

Replaces the old "run this UPDATE by hand in psql" instruction in the
README - same effect (flips users.role), just a command instead of raw SQL,
so nobody needs direct database access just to get admin rights for testing.

Usage:
    python -m backend.scripts.make_admin someone@example.com
    python -m backend.scripts.make_admin someone@example.com --demote
"""
import argparse

from sqlalchemy.orm import Session

from backend.database.models import User
from backend.database.session import SessionLocal


def set_role(db: Session, email: str, role: str) -> str:
    """Core logic, split out from main() so it's testable without going
    through argparse/SessionLocal. Returns a human-readable result message;
    raises ValueError if no user is registered with that email."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise ValueError(f"No user registered with email {email!r} - register them first, then rerun this.")

    if user.role == role:
        return f"{email} is already {role!r} - nothing to do."

    old_role = user.role
    user.role = role
    db.commit()
    return f"{email}: role {old_role!r} -> {role!r}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote (or demote) a user to/from admin")
    parser.add_argument("email", help="Email of an already-registered user")
    parser.add_argument(
        "--demote", action="store_true",
        help="Set role back to 'student' instead of promoting to 'admin'",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print(set_role(db, args.email, "student" if args.demote else "admin"))
    except ValueError as exc:
        raise SystemExit(str(exc))
    finally:
        db.close()


if __name__ == "__main__":
    main()
