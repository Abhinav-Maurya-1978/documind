"""Helper script to push local DocuMind repository to a remote GitHub repository using Dulwich."""
import sys
from pathlib import Path
from dulwich import porcelain
from dulwich.repo import Repo

def push_to_remote(remote_url: str):
    repo_path = Path(__file__).resolve().parent.parent
    repo = Repo(str(repo_path))

    print(f"Configuring remote 'origin': {remote_url}")
    try:
        porcelain.remote_add(repo, "origin", remote_url)
    except Exception:
        # Remote may already exist, update it
        config = repo.get_config()
        config.set((b"remote", b"origin"), b"url", remote_url.encode("utf-8"))
        config.write_to_path()

    print("Pushing commits to remote repository...")
    porcelain.push(repo, remote_url, refspecs=["refs/heads/master:refs/heads/main"])
    print("Push complete!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/push_to_github.py <github_repo_url>")
        print("Example: python scripts/push_to_github.py https://github.com/USERNAME/documind.git")
        sys.exit(1)

    push_to_remote(sys.argv[1])
