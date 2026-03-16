import requests
import base64
import os
from log_config import get_logger

log = get_logger("github_publisher")


class GitHubPublisher:
    def __init__(self, token, repo):
        self.token = token
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{repo}/contents"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        if not token:
            log.warning(
                "GitHubPublisher initialised WITHOUT a token — all publishes will be skipped"
            )
        else:
            log.debug("GitHubPublisher initialised for repo: %s", repo)

    def publish_file(self, path, content, message):
        """Publishes or updates a file in the repo."""
        if not self.token:
            log.warning("Skipping GitHub publish (no token): %s", path)
            return

        url = f"{self.base_url}/{path}"
        log.info("Publishing to GitHub: %s (%d bytes)", path, len(content))

        # 1. Get current file (to get SHA if it exists)
        sha = None
        log.debug("Checking for existing file SHA: GET %s", url)
        r = requests.get(url, headers=self.headers)
        if r.status_code == 200:
            sha = r.json()["sha"]
            log.debug("Existing file found, SHA=%s", sha)
        elif r.status_code == 404:
            log.debug("File does not exist yet — will create")
        else:
            log.warning(
                "Unexpected status checking file existence: %d %s",
                r.status_code,
                r.text,
            )

        # 2. Upload
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha

        log.debug("Uploading file: PUT %s (commit: %s)", url, message)
        r = requests.put(url, headers=self.headers, json=payload)
        if r.status_code in [200, 201]:
            action = "updated" if sha else "created"
            log.info("GitHub publish successful (%s): %s", action, path)
        else:
            log.error(
                "GitHub publish FAILED for %s: HTTP %d — %s",
                path,
                r.status_code,
                r.text,
            )
