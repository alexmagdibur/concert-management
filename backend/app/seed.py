"""Run explicitly: python -m app.seed --confirm-test-data."""

import argparse
import json
import sys

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.services.seed import SeedError, seed_connection, validate_target


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a dedicated PostgreSQL test database")
    parser.add_argument("--confirm-test-data", action="store_true")
    args = parser.parse_args()
    engine = None
    try:
        settings = get_settings()
        if settings.seed_database_url is None:
            raise SeedError(
                "Set SEED_DATABASE_URL explicitly; application DATABASE_URL is never used"
            )
        url = str(settings.seed_database_url)
        validate_target(settings, url, confirmed=args.confirm_test_data)
        engine = create_engine(url)
        with engine.begin() as conn:
            counts = seed_connection(conn, settings, confirmed=args.confirm_test_data)
        print(json.dumps(counts, indent=2))
        return 0
    except SeedError as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 1
    except ValidationError:
        print("Seed refused: invalid environment configuration", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Seed failed; transaction rolled back. Check PostgreSQL and applied migrations.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
