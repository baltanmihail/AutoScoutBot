"""
Railway unified startup script.

Handles:
    1. Database migration (creates tables, migrates CSV data)
    2. Starts FastAPI backend (uvicorn) in background
    3. Starts Telegram bot in foreground

Usage:
    python railway_start.py          # full startup (migration + api + bot)
    python railway_start.py --web    # web only (FastAPI)
    python railway_start.py --bot    # bot only
"""

import asyncio
import os
import sys
import subprocess
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")


def check_ml_models():
    """Check if trained ML models are available."""
    from pathlib import Path
    model_dir = Path("scoring/models/overall")
    joblib_files = list(model_dir.glob("*.joblib")) if model_dir.exists() else []
    if joblib_files:
        print(f"  ML models found: {len(joblib_files)} files in scoring/models/overall/")
        return True
    print("  ML models NOT found -- bot will use heuristic scoring")
    return False


async def run_db_migration():
    """Run database migration if DATABASE_URL is set."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("  No DATABASE_URL set, skipping PostgreSQL migration")
        print("  Bot will use local CSV + ML scoring")
        return

    print("  Migrating data to PostgreSQL...")
    try:
        from backend.migrate_csv import migrate
        csv_path = os.environ.get("SKOLKOVO_DATABASE_PATH", "SkolkovoStartups.csv")
        await migrate(csv_path)
        print("  Database migration complete")
    except Exception as e:
        print(f"  Migration error (non-fatal): {e}")
        print("  Bot will still work with CSV data")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", action="store_true", help="Start FastAPI only")
    parser.add_argument("--bot", action="store_true", help="Start bot only")
    args = parser.parse_args()

    port = os.environ.get("PORT", "8000")

    print("=" * 60)
    print("  AutoScoutBot -- Railway Startup")
    print("=" * 60)

    # Step 1: Check ML models
    print("\n[1/3] Checking ML models...")
    check_ml_models()

    # Step 2: Database migration
    if not args.bot:
        print("\n[2/3] Database initialization...")
        asyncio.run(run_db_migration())
    else:
        print("\n[2/3] Skipping DB migration (--bot mode)")

    # Step 3: Start services
    print("\n[3/3] Starting services...")

    if args.web:
        print(f"  Starting FastAPI on port {port}...")
        os.execvp(
            sys.executable,
            [sys.executable, "-m", "uvicorn", "backend.app:app",
             "--host", "0.0.0.0", "--port", port],
        )

    elif args.bot:
        print("  Starting Telegram bot...")
        os.execvp(sys.executable, [sys.executable, "bot.py"])

    else:
        # Full mode: FastAPI in background, bot in foreground
        print(f"  Starting FastAPI on port {port} (background)...")
        web_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app:app",
             "--host", "0.0.0.0", "--port", port],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        time.sleep(2)

        print("  Starting Telegram bot (foreground)...")
        try:
            os.execvp(sys.executable, [sys.executable, "bot.py"])
        finally:
            web_proc.terminate()


if __name__ == "__main__":
    main()
