"""Backend-only management commands."""

from __future__ import annotations

import argparse
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import OWNER_ROLE, ensure_roles
from app.db.session import SessionLocal
from app.models import Role, User


class SetOwnerResult(TypedDict):
    user_code: str
    previous_owner_codes: list[str]
    changed: bool


def set_owner(db: Session, user_code: str) -> SetOwnerResult:
    """Make one active account the unique owner in a single transaction."""
    normalized_code = str(user_code or "").strip()
    if not normalized_code:
        raise ValueError("user_code cannot be empty")

    try:
        roles = ensure_roles(db, commit=False)
        owner_role = db.scalar(
            select(Role)
            .where(Role.name == OWNER_ROLE)
            .with_for_update()
        )
        if owner_role is None:
            raise RuntimeError("owner role was not initialized")
        target = db.scalar(
            select(User)
            .options(selectinload(User.roles))
            .where(User.user_code == normalized_code)
        )
        if target is None:
            raise ValueError(f"user not found: {normalized_code}")
        if not target.is_active:
            raise ValueError(f"user is inactive: {normalized_code}")

        admin_role = roles["admin"]
        target_was_owner = target.has_role(OWNER_ROLE)
        current_owners = db.scalars(
            select(User)
            .options(selectinload(User.roles))
            .where(User.roles.any(Role.name == OWNER_ROLE))
        ).all()
        previous_owner_codes: list[str] = []
        for current_owner in current_owners:
            if current_owner.id == target.id:
                continue
            previous_owner_codes.append(current_owner.user_code)
            current_owner.roles = [role for role in current_owner.roles if role.name != OWNER_ROLE]
            if not current_owner.has_role("admin"):
                current_owner.roles.append(admin_role)

        if not target_was_owner:
            target.roles.append(owner_role)

        db.commit()
        return {
            "user_code": target.user_code,
            "previous_owner_codes": previous_owner_codes,
            "changed": bool(previous_owner_codes) or not target_was_owner,
        }
    except Exception:
        db.rollback()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backend management commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_owner_parser = subparsers.add_parser("set-owner", help="grant the unique owner role")
    set_owner_parser.add_argument("--user-code", required=True, help="existing active account code")
    args = parser.parse_args(argv)

    if args.command == "set-owner":
        try:
            with SessionLocal() as db:
                result = set_owner(db, args.user_code)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"owner set to {result['user_code']}")
        if result["previous_owner_codes"]:
            print(f"previous owners demoted: {', '.join(result['previous_owner_codes'])}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
