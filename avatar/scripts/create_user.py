"""Create an organization and its first user from the command line.

Use this for the very first (platform admin) account, or whenever public
sign-up is disabled:

    uv run python -m scripts.create_user --email you@company.com \
        --name "Your Name" --org "Your Company" --platform-admin

The password is prompted for (never passed on the command line, where it would
end up in shell history).
"""

import argparse
import asyncio
import getpass
import sys

from core.auth import AuthStore


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--org", required=True, help="organization name (created)")
    parser.add_argument("--role", choices=["admin", "recruiter"], default="admin")
    parser.add_argument(
        "--platform-admin",
        action="store_true",
        help="can see workers/streams/demo and data of every organization",
    )
    args = parser.parse_args()

    password = getpass.getpass("Password (10+ characters): ")
    if len(password) < 10:
        print("Password must be at least 10 characters", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords don't match", file=sys.stderr)
        return 1

    store = AuthStore()
    org_id = await store.create_org(args.org)
    try:
        user_id = await store.create_user(
            email=args.email,
            name=args.name,
            password=password,
            org_id=org_id,
            role=args.role,
            is_platform_admin=args.platform_admin,
        )
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Created {user_id} ({args.email}) in organization {org_id} ({args.org})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
