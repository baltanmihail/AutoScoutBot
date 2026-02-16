"""
Nuclear git fix: abort rebase, create clean commit, force push.
Run: python _git_nuclear_fix.py
"""
import subprocess
import os
import shutil

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run(cmd):
    print(f"\n$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    out = (r.stdout.strip() + "\n" + r.stderr.strip()).strip()
    if out:
        print(out)
    return r.returncode

print("=" * 60)
print("  NUCLEAR GIT FIX")
print("  Abort rebase -> clean commit -> force push")
print("=" * 60)

# Step 1: Remove ALL lock files
for lock in [".git/index.lock", ".git/rebase-merge", ".git/rebase-apply"]:
    full = os.path.join(os.getcwd(), lock)
    if os.path.exists(full):
        try:
            if os.path.isdir(full):
                shutil.rmtree(full, ignore_errors=True)
                # If rmtree failed silently, try cmd
                if os.path.exists(full):
                    os.system(f'rmdir /s /q "{full}"')
                print(f"[OK] Removed directory: {lock}")
            else:
                os.remove(full)
                print(f"[OK] Removed file: {lock}")
        except Exception as e:
            print(f"[WARN] Could not remove {lock}: {e}")
            print(f"       Trying via cmd...")
            os.system(f'rmdir /s /q "{full}" 2>nul')
            os.system(f'del /f /q "{full}" 2>nul')

# Step 2: Abort rebase
print("\n--- Step 1: Abort rebase ---")
run("git rebase --abort")

# Step 3: Check status
print("\n--- Step 2: Current status ---")
run("git status")
run("git log --oneline -3")

# Step 4: Stage EVERYTHING
print("\n--- Step 3: Stage all changes ---")
run("git add -A")

# Force-add .joblib models (in case gitignore blocks them)
import glob
joblib_files = glob.glob("scoring/models/**/*.joblib", recursive=True)
print(f"\nFound {len(joblib_files)} .joblib model files")
for f in joblib_files:
    run(f'git add --force "{f}"')

# Force-add CSV
if os.path.exists("SkolkovoStartups.csv"):
    run('git add --force SkolkovoStartups.csv')
    print("[OK] CSV added")

# Step 5: Show staged
print("\n--- Step 4: Staged files ---")
run("git status --short")

# Step 6: Commit
print("\n--- Step 5: Commit ---")
code = run('git commit -m "v2: ML scoring + FastAPI + all models"')

# Step 7: Force push (overwrite remote)
print("\n--- Step 6: Force push ---")
print("\nWARNING: This will overwrite the remote branch!")
answer = input("Proceed with force push? (y/n): ").strip().lower()
if answer == "y":
    run("git push --force origin main")
    print("\n[OK] Force pushed! Railway will redeploy.")
else:
    print("\nSkipped. Run manually: git push --force origin main")

# Final status
print("\n--- Final status ---")
run("git log --oneline -5")
run("git status")
