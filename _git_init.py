"""Quick git init helper -- run: python _git_init.py"""
import subprocess, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
def run(cmd):
    print(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout: print(r.stdout.strip())
    if r.stderr: print(r.stderr.strip())
    return r.returncode

run("git init")
run("git add -A")
run('git commit -m "AutoScoutBot v2: ML scoring (LightGBM R2>0.96) + FastAPI + Telegram bot"')
run("git status")
print("\nDone! Next:")
print("  1. GitHub: https://github.com/new -> create AutoScoutBot repo")
print("  2. git remote add origin https://github.com/YOUR_USER/AutoScoutBot.git")
print("  3. git branch -M main")
print("  4. git push -u origin main")
print("  5. Railway: connect GitHub repo")
