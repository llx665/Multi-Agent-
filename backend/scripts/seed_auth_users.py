from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(backend_root))

from app.services.auth_mysql_bootstrap import ensure_seed_users


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ensure auth seed users exist in the target database.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--password", default="ChangeMe123!")
    args = parser.parse_args(argv)

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    result = ensure_seed_users(args.database_url, seed_password=args.password)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
