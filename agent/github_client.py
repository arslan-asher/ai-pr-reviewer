import os
import sys
import json
import requests
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

class GitHubClient:
    def __init__(self, token: Optional[str] = None, repository: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.repository = repository or os.environ.get("GITHUB_REPOSITORY")
        self.base_url = "https://api.github.com"
        
        if not self.token:
            print("⚠️ Warning: GITHUB_TOKEN is not set. GitHub API calls will be unauthorized or simulated.")

    @property
    def headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Code-Reviewer-Agent/1.0"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_pr(self, pull_number: int) -> Dict[str, Any]:
        """Fetch Pull Request details including title, description, commits, author, base, head."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pull_number}"
        res = requests.get(url, headers=self.headers, timeout=30)
        res.raise_for_status()
        return res.json()

    def get_pr_diff(self, pull_number: int) -> str:
        """Fetch unified raw git diff of the Pull Request."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pull_number}"
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()
        return res.text

    def get_pr_files(self, pull_number: int) -> List[Dict[str, Any]]:
        """Fetch list of changed files with patch hunks."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pull_number}/files"
        files = []
        page = 1
        while True:
            res = requests.get(f"{url}?page={page}&per_page=100", headers=self.headers, timeout=30)
            res.raise_for_status()
            data = res.json()
            if not data:
                break
            files.extend(data)
            if len(data) < 100:
                break
            page += 1
        return files

    def get_existing_review_comments(self, pull_number: int) -> List[Dict[str, Any]]:
        """Fetch existing line-by-line review comments on the PR."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pull_number}/comments"
        res = requests.get(url, headers=self.headers, timeout=30)
        if res.status_code == 200:
            return res.json()
        return []

    def post_pr_review(self, pull_number: int, summary_body: str, inline_comments: List[Dict[str, Any]], commit_id: str = None) -> Dict[str, Any]:
        """
        Creates a formal Pull Request Review containing:
        1. High-level Summary body (Walkthrough, Safety checklist, Mermaid diagram)
        2. Array of inline review comments attached to precise files, lines, and 1-click suggestions.
        """
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pull_number}/reviews"
        
        # Filter and validate comments
        formatted_comments = []
        for c in inline_comments:
            if not c.get("path") or not c.get("line") or not c.get("body"):
                continue
            formatted_comments.append({
                "path": c["path"],
                "line": int(c["line"]),
                "side": c.get("side", "RIGHT"),
                "body": c["body"]
            })

        payload = {
            "body": summary_body,
            "event": "COMMENT",
            "comments": formatted_comments
        }
        if commit_id:
            payload["commit_id"] = commit_id

        res = requests.post(url, headers=self.headers, json=payload, timeout=30)
        
        # If batch review creation fails with position error, fall back to individual comments
        if res.status_code not in (200, 201):
            print(f"⚠️ Batch review creation returned {res.status_code}: {res.text}. Falling back to top-level comment + individual comments.")
            self.post_issue_comment(pull_number, summary_body)
            for comment in formatted_comments:
                self.post_single_review_comment(pull_number, comment, commit_id)
            return {"status": "fallback_individual_comments"}
            
        return res.json()

    def post_single_review_comment(self, pull_number: int, comment: Dict[str, Any], commit_id: str) -> Optional[Dict[str, Any]]:
        """Post a single inline review comment on a specific line."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pull_number}/comments"
        payload = {
            "body": comment["body"],
            "path": comment["path"],
            "line": int(comment["line"]),
            "side": comment.get("side", "RIGHT"),
            "commit_id": commit_id
        }
        res = requests.post(url, headers=self.headers, json=payload, timeout=30)
        if res.status_code in (200, 201):
            return res.json()
        print(f"⚠️ Could not post inline comment on {comment['path']}:{comment['line']}: {res.text}")
        return None

    def post_issue_comment(self, issue_or_pr_number: int, body: str) -> Dict[str, Any]:
        """Post top-level issue / PR comment."""
        url = f"{self.base_url}/repos/{self.repository}/issues/{issue_or_pr_number}/comments"
        res = requests.post(url, headers=self.headers, json={"body": body}, timeout=30)
        res.raise_for_status()
        return res.json()

    def reply_to_review_comment(self, pull_number: int, comment_id: int, body: str) -> Dict[str, Any]:
        """Reply inside an existing review comment thread."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pull_number}/comments/{comment_id}/replies"
        res = requests.post(url, headers=self.headers, json={"body": body}, timeout=30)
        res.raise_for_status()
        return res.json()

    def add_reaction(self, comment_id: int, reaction: str = "eyes", is_review_comment: bool = False) -> None:
        """Add reaction emoji (e.g. eyes, rocket, +1) to acknowledge developer commands."""
        target = "pulls" if is_review_comment else "issues"
        url = f"{self.base_url}/repos/{self.repository}/{target}/comments/{comment_id}/reactions"
        headers = {**self.headers, "Accept": "application/vnd.github.squirrel-girl-preview+json"}
        try:
            requests.post(url, headers=headers, json={"content": reaction}, timeout=10)
        except Exception:
            pass
