"""
Fix: add CSV + scoring models to git and push.
Run: python _git_push_fix.py
"""
import subprocess
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run(cmd):
    print(f"\n$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())
    return r.returncode

print("=" * 60)
print("  Fix: add CSV data + push to Railway")
print("=" * 60)

# Remove lock if stuck
lock = os.path.join(".git", "index.lock")
if os.path.exists(lock):
    os.remove(lock)
    print("[OK] Removed index.lock")

# Force-add CSV (was gitignored, now allowed)
run("git add --force SkolkovoStartups.csv")

# Add everything else
run("git add -A")

# Show what's staged
run("git status --short")

# Commit
run('git commit -m "fix: add CSV data + ML models for Railway deploy"')

# Push
run("git push origin main")

print("\n" + "=" * 60)
print("  Done! Railway should auto-deploy now.")
print("  Next: set environment variables in Railway Dashboard")
print("=" * 60)
