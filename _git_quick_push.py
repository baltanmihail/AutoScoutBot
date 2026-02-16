"""Quick commit + push. Run: python _git_quick_push.py"""
import subprocess, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
def run(cmd):
    print(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip(): print(r.stdout.strip())
    if r.stderr.strip(): print(r.stderr.strip())

lock = os.path.join(".git", "index.lock")
if os.path.exists(lock): os.remove(lock)

run("git add -A")
run("git status --short")
run('git commit -m "fix: restore ML scoring integration in bot.py + analyze_startup"')
run("git push origin main")
print("\nDone! Railway will auto-deploy.")
