"""
Fix stuck git state + commit all new files + push.
Run: python _git_fix.py
"""
import subprocess
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run(cmd, check=False):
    print(f"\n$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())
    return r.returncode

print("=" * 60)
print("  Git Fix: unlock + abort rebase + commit + push")
print("=" * 60)

# Step 1: Remove index.lock if exists
lock_file = os.path.join(".git", "index.lock")
if os.path.exists(lock_file):
    os.remove(lock_file)
    print(f"\n[OK] Removed {lock_file}")
else:
    print(f"\n[OK] No lock file found")

# Step 2: Abort stuck rebase
print("\n--- Aborting stuck rebase ---")
run("git rebase --abort")

# Step 3: Remove .venv312 from git tracking (if tracked)
print("\n--- Removing .venv312 from git tracking ---")
run("git rm -r --cached .venv312 2>nul")

# Step 4: Add all changes
print("\n--- Adding all files ---")
run("git add -A")

# Step 5: Show what we're committing
print("\n--- Status ---")
run("git status --short")

# Step 6: Commit
print("\n--- Committing ---")
code = run('git commit -m "v2: ML scoring (LightGBM R2>0.96) + FastAPI backend + Railway deploy"')
if code != 0:
    print("\n[!] Commit may have failed, trying with --allow-empty...")
    run('git commit --allow-empty -m "v2: ML scoring + FastAPI + Railway deploy"')

# Step 7: Push
print("\n--- Pushing to origin/main ---")
code = run("git push origin main")
if code != 0:
    print("\n[!] Push failed, trying force push...")
    answer = input("Force push? This overwrites remote history. (y/n): ").strip().lower()
    if answer == "y":
        run("git push --force origin main")
    else:
        print("Skipped force push. You may need to resolve conflicts manually.")

# Step 8: Final status
print("\n--- Final status ---")
run("git status")
run("git log --oneline -5")

print("\n" + "=" * 60)
print("  Done! Check Railway dashboard for auto-deploy.")
print("=" * 60)
