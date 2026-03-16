import requests
import base64
import os


class GitHubPublisher:
    def __init__(self, token, repo):
        self.token = token
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{repo}/contents"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def publish_file(self, path, content, message):
        """Publishes or updates a file in the repo."""
        if not self.token:
            print(f"Skipping GitHub publish (no token): {path}")
            return

        url = f"{self.base_url}/{path}"

        # 1. Get current file (to get SHA if it exists)
        sha = None
        r = requests.get(url, headers=self.headers)
        if r.status_code == 200:
            sha = r.json()["sha"]

        # 2. Upload
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(url, headers=self.headers, json=payload)
        if r.status_code in [200, 201]:
            print(f"Successfully published to GitHub: {path}")
        else:
            print(f"Error publishing to GitHub: {r.status_code} {r.text}")
