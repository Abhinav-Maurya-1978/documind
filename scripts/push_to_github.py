"""Helper script to push local DocuMind repository to a remote GitHub repository using Dulwich."""
import getpass
import re
import sys
from pathlib import Path
from dulwich import porcelain
from dulwich.repo import Repo

def push_to_remote(remote_url: str, token: str = None):
    repo_path = Path(__file__).resolve().parent.parent
    repo = Repo(str(repo_path))

    # If the URL is HTTPS and does not already contain credentials, prompt for token
    push_url = remote_url
    if remote_url.startswith("https://") and "@" not in remote_url:
        if not token:
            print("\nGitHub requires a Personal Access Token to push.")
            print("To generate one (30 seconds):")
            print("1. Visit: https://github.com/settings/tokens/new")
            print("2. Set Note (e.g. 'DocuMind Deploy') and tick the 'repo' scope checkbox.")
            print("3. Click 'Generate token' and copy it.\n")
            token = getpass.getpass("Paste your GitHub Personal Access Token: ").strip()

        if token:
            # Embed token into URL safely for this push
            clean_url = re.sub(r"^https://", "", remote_url)
            push_url = f"https://oauth2:{token}@{clean_url}"

    print(f"Configuring remote 'origin': {remote_url}")
    try:
        porcelain.remote_add(repo, "origin", remote_url)
    except Exception:
        # Remote may already exist, update it
        config = repo.get_config()
        config.set((b"remote", b"origin"), b"url", remote_url.encode("utf-8"))
        config.write_to_path()

    print("Pushing commits to remote repository (main branch)...")
    try:
        porcelain.push(repo, push_url, refspecs=["refs/heads/master:refs/heads/main"])
        print("\nSUCCESS! All code has been pushed to your GitHub repository:")
        print(f"   {remote_url}")
    except Exception as e:
        # Also try pushing master branch name directly
        try:
            porcelain.push(repo, push_url, refspecs=["refs/heads/master:refs/heads/master"])
            print("\nSUCCESS! All code has been pushed to your GitHub repository (master branch):")
            print(f"   {remote_url}")
        except Exception as e2:
            print(f"\nPush failed: {e2}")
            raise

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/Abhinav-Maurya-1978/documind.git"
    token_arg = sys.argv[2] if len(sys.argv) > 2 else None
    push_to_remote(url, token_arg)
