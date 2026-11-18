"""Create the initial administrator using local database access."""

import argparse
from getpass import getpass

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.database import SessionLocal
from app.schemas.access import AccountCreate
from app.services.users import UserService


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first active administrator")
    parser.add_argument("--login", required=True)
    parser.add_argument("--full-name", required=True)
    args = parser.parse_args()
    password = getpass("Password: ")
    if password != getpass("Confirm password: "):
        parser.error("Passwords differ")
    try:
        data = AccountCreate(
            login=args.login,
            full_name=args.full_name,
            position="Administrator",
            password=password,
            roles=["ADMIN"],
        )
        with SessionLocal() as session:
            result = UserService(session).create(data, actor=None)
    except ValidationError:
        parser.error(
            "Invalid account details or password shorter than 12 or longer than 256 characters"
        )
    except HTTPException as exc:
        parser.error(str(exc.detail))
    print(f"Administrator created: account {result.id}")


if __name__ == "__main__":
    main()
