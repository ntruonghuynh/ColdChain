"""Local administrative password setup/rotation helper; prompts without echoing the secret."""

import argparse
import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import AppUser
from app.db.session import get_sessionmaker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    first = getpass.getpass("New local-demo password (minimum 12 characters): ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        parser.error("passwords do not match")
    try:
        encoded = hash_password(first)
    except ValueError as exc:
        parser.error(str(exc))
    with get_sessionmaker()() as session:
        user = session.scalar(select(AppUser).where(AppUser.username == args.username))
        if user is None or args.username == "monitor.service":
            parser.error("unknown or non-login user")
        user.password_hash = encoded
        session.commit()
    print(f"Password updated for {args.username}.")


if __name__ == "__main__":
    main()
