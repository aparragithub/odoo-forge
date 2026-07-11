#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path


def wait_for_psql(db_host, db_port, db_user, db_password_file, database, timeout):
    import psycopg2

    db_password = Path(db_password_file).read_text(encoding="utf-8")
    start_time = time.time()
    while True:
        try:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=database,
                connect_timeout=5,
            )
            conn.close()
            print("PostgreSQL is ready!")
            return True
        except psycopg2.OperationalError:
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                print(
                    f"Timeout reached ({timeout}s). "
                    f"PostgreSQL is not available at {db_host}:{db_port}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"PostgreSQL not ready yet, retrying... ({int(elapsed_time)}s)", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wait for PostgreSQL to be ready.")
    parser.add_argument("--db_host", default="db", help="PostgreSQL host")
    parser.add_argument("--db_port", default=5432, type=int, help="PostgreSQL port")
    parser.add_argument("--db_user", default="odoo", help="PostgreSQL user")
    parser.add_argument("--db_password_file", required=True, help="Path to the PostgreSQL password")
    parser.add_argument("--database", default="postgres", help="PostgreSQL database")
    parser.add_argument("--timeout", default=60, type=int, help="Total timeout in seconds")
    args = parser.parse_args()
    wait_for_psql(
        args.db_host, args.db_port, args.db_user, args.db_password_file, args.database, args.timeout
    )
