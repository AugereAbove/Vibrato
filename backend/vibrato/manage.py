from __future__ import annotations

import argparse
import os
import sys

from .config import get_settings
from .db import connection
from .services import auth_service


def main() -> None:
    parser = argparse.ArgumentParser(prog="vibrato.manage", description="Manage tester access on a running install.")
    commands = parser.add_subparsers(dest="command", required=True)
    invite = commands.add_parser("invite", help="Create a tester with a single-use sign-in link that never expires.")
    invite.add_argument("name", nargs="?", default="Tester")
    commands.add_parser("list", help="List testers and their unused links.")
    args = parser.parse_args()

    if "VIBRATO_DATA_DIR" not in os.environ:
        sys.exit("Set VIBRATO_DATA_DIR to the install's data folder, e.g. VIBRATO_DATA_DIR=/opt/vibrato/data")
    settings = get_settings()
    if not settings.db_path.exists():
        sys.exit(f"No database at {settings.db_path}. Check VIBRATO_DATA_DIR.")
    connection._db = connection.Database(settings.db_path, settings.backups_dir)
    if args.command == "invite":
        link = auth_service.create_tester(args.name)
        print(f"Single-use link for {args.name}:")
        print(f"/api/auth/claim/{link['code']}")
    else:
        for tester in auth_service.list_testers():
            state = "revoked" if tester["disabled"] else (tester["pending_code"] or "link already used")
            print(f"{tester['display_name']}: {state}")


if __name__ == "__main__":
    main()
