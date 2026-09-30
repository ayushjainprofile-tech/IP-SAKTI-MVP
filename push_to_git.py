import subprocess
import os

repo_dir = "/disk/ayush /college project/sih/sih final mam/IP-SAKTI-MVP"

def run_git():
    print(f"Checking git status in {repo_dir}...")
    st = subprocess.run(["git", "status"], cwd=repo_dir, capture_output=True, text=True)
    print("STDOUT:\n", st.stdout)
    print("STDERR:\n", st.stderr)

    print("\nAdding updated files...")
    subprocess.run(["git", "add", "."], cwd=repo_dir)

    print("\nCommitting changes...")
    commit_res = subprocess.run(["git", "commit", "-m", "fix: blend ProductContextEngine confidence in calculate_confidence for 80%+ score on classical formulations"], cwd=repo_dir, capture_output=True, text=True)
    print("COMMIT STDOUT:\n", commit_res.stdout)
    print("COMMIT STDERR:\n", commit_res.stderr)

    print("\nPushing to GitHub...")
    push_res = subprocess.run(["git", "push"], cwd=repo_dir, capture_output=True, text=True)
    print("PUSH STDOUT:\n", push_res.stdout)
    print("PUSH STDERR:\n", push_res.stderr)

if __name__ == "__main__":
    run_git()
