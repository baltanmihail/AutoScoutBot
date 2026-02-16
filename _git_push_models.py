"""
Force-add ML model files (.joblib) to git and push.
Run: python _git_push_models.py
"""
import subprocess
import os
import glob

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run(cmd):
    print(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())
    return r.returncode

# Remove lock if exists
lock = os.path.join(".git", "index.lock")
if os.path.exists(lock):
    os.remove(lock)
    print("[OK] Removed index.lock")

# Find all .joblib files
joblib_files = glob.glob("scoring/models/**/*.joblib", recursive=True)
json_files = glob.glob("scoring/models/**/*.json", recursive=True)

print(f"\nFound {len(joblib_files)} .joblib files:")
for f in joblib_files:
    size_kb = os.path.getsize(f) / 1024
    print(f"  {f} ({size_kb:.0f} KB)")

print(f"\nFound {len(json_files)} .json meta files:")
for f in json_files:
    print(f"  {f}")

if not joblib_files:
    print("\n[ERROR] No .joblib files found!")
    print("Run 'python run_train.py' first to train the models.")
    exit(1)

# Force-add all model files
print("\n--- Force-adding model files ---")
for f in joblib_files + json_files:
    run(f'git add --force "{f}"')

# Also add everything else that changed
run("git add -A")
run("git status --short")

# Commit
run('git commit -m "fix: add ML model files (.joblib) for Railway"')

# Push
run("git push origin main")

print("\n[OK] Models pushed! Railway will redeploy with ML scoring.")
