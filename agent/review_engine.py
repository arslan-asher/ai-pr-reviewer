import os
import sys
import json
import argparse
import subprocess
from typing import Dict, Any, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure directory is on path for both local and action invocation
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import ReviewConfig
from diff_parser import DiffParser
from github_client import GitHubClient
from gemini_reviewer import GeminiReviewer

class ReviewEngine:
    def __init__(self, config: Optional[ReviewConfig] = None):
        self.config = config or ReviewConfig.load()
        self.github = GitHubClient()
        self.reviewer = GeminiReviewer(config=self.config)

    def run_github_event(self) -> None:
        """Main dispatcher for GitHub Actions triggers."""
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        event_name = os.environ.get("GITHUB_EVENT_NAME", "pull_request")

        if not event_path or not os.path.exists(event_path):
            print("❌ Error: GITHUB_EVENT_PATH not set or file not found.")
            sys.exit(1)

        with open(event_path, "r", encoding="utf-8") as f:
            event_data = json.load(f)

        print(f"🚀 Received GitHub Event: '{event_name}'")

        if event_name in ("pull_request", "pull_request_target"):
            self.handle_pull_request_event(event_data)
        elif event_name in ("issue_comment", "pull_request_review_comment"):
            self.handle_comment_event(event_data, is_review_comment=(event_name == "pull_request_review_comment"))
        else:
            print(f"ℹ️ Event '{event_name}' not targeted for automated review. Exiting gracefully.")

    def handle_pull_request_event(self, event_data: Dict[str, Any]) -> None:
        """Processes a Pull Request open/synchronize event."""
        action = event_data.get("action")
        pr = event_data.get("pull_request", {})
        pr_number = pr.get("number")
        head_sha = pr.get("head", {}).get("sha")

        print(f"📋 Processing PR #{pr_number} (action: {action}, head: {head_sha})")

        if not pr_number:
            print("❌ No PR number found in event payload.")
            return

        # 1. Fetch raw diff from GitHub API
        try:
            raw_diff = self.github.get_pr_diff(pr_number)
        except Exception as e:
            print(f"⚠️ Failed to fetch PR diff via GitHub API ({e}). Attempting local git diff.")
            raw_diff = self._get_local_git_diff()

        if not raw_diff or not raw_diff.strip():
            print("ℹ️ Diff is empty. Nothing to review.")
            return

        # 2. Parse diff into structured hunks
        file_diffs = DiffParser.parse_patch(raw_diff)
        print(f"🔍 Parsed {len(file_diffs)} changed files from PR diff.")

        # 3. Fetch other open PRs for cross-PR impact detection
        other_prs = self.github.get_all_open_prs(pr_number) if pr_number else []

        # 4. Generate Gemini AI Review
        review_result = self.reviewer.generate_review(
            pr_meta=pr,
            file_diffs=file_diffs,
            full_patch=raw_diff,
            related_prs=other_prs
        )

        summary_body = review_result.get("summary", "")
        inline_comments = review_result.get("inline_comments", [])

        print(f"📝 Generated summary + {len(inline_comments)} inline suggestions.")

        # 4. Post Review to GitHub
        try:
            res = self.github.post_pr_review(
                pull_number=pr_number,
                summary_body=summary_body,
                inline_comments=inline_comments,
                commit_id=head_sha
            )
            print(f"✅ Successfully posted review to PR #{pr_number}!")
        except Exception as e:
            print(f"❌ Error posting review to GitHub: {e}")

    def handle_comment_event(self, event_data: Dict[str, Any], is_review_comment: bool = False) -> None:
        """Processes interactive chat mentions like '@ai-reviewer explain'."""
        comment = event_data.get("comment", {})
        comment_body = comment.get("body", "")
        comment_id = comment.get("id")
        
        pr_info = event_data.get("issue", {}).get("pull_request") if not is_review_comment else True
        if not pr_info:
            print("ℹ️ Comment is on an issue, not a Pull Request. Skipping.")
            return

        issue_or_pr_number = event_data.get("issue", {}).get("number") or event_data.get("pull_request", {}).get("number")

        bot_trigger = f"@{self.config.bot_name}"
        if bot_trigger not in comment_body:
            print(f"ℹ️ Comment does not contain bot trigger '{bot_trigger}'. Skipping.")
            return

        # React with 👀 emoji
        if comment_id:
            self.github.add_reaction(comment_id, reaction="eyes", is_review_comment=is_review_comment)

        print(f"💬 Handling interactive chat mention in comment #{comment_id}: '{comment_body}'")

        # Check if developer requested a full re-review
        if f"{bot_trigger} review" in comment_body:
            pr = self.github.get_pr(issue_or_pr_number)
            self.handle_pull_request_event({"action": "synchronize", "pull_request": pr})
            return

        # Handle QA / Explain questions
        context = {
            "pr_title": f"PR #{issue_or_pr_number}",
            "thread_context": comment_body
        }
        answer = self.reviewer.answer_interactive_chat(query=comment_body, context=context)

        if is_review_comment and comment_id:
            self.github.reply_to_review_comment(issue_or_pr_number, comment_id, answer)
        else:
            self.github.post_issue_comment(issue_or_pr_number, answer)

        print(f"✅ Replied to interactive chat query on PR #{issue_or_pr_number}")

    def run_local_review(self, diff_text: Optional[str] = None) -> None:
        """Runs the reviewer locally on terminal git diff for testing in VS Code or CLI."""
        raw_diff = diff_text or self._get_local_git_diff()
        if not raw_diff.strip():
            print("ℹ️ No uncommitted changes or diff found.")
            return

        file_diffs = DiffParser.parse_patch(raw_diff)
        print(f"\n=======================================================")
        print(f"🤖 AI CODE REVIEWER (LOCAL / IDE PREVIEW)")
        print(f"=======================================================")
        print(f"Analyzing {len(file_diffs)} modified files...\n")

        review_result = self.reviewer.generate_review(
            pr_meta={"title": "Local Workspace Changes", "body": "Local developer working tree diff."},
            file_diffs=file_diffs,
            full_patch=raw_diff
        )

        print(review_result.get("summary", ""))
        print("\n-------------------------------------------------------")
        print(f"🔍 LINE-BY-LINE INLINE SUGGESTIONS ({len(review_result.get('inline_comments', []))})")
        print("-------------------------------------------------------")

        for comment in review_result.get("inline_comments", []):
            print(f"\n📍 File: {comment['path']} (Line {comment['line']}):")
            print(comment["body"])

    def _get_local_git_diff(self) -> str:
        """Helper to get current git diff from local working tree."""
        try:
            res = subprocess.run(["git", "diff", "HEAD~1"], capture_output=True, text=True)
            if not res.stdout:
                res = subprocess.run(["git", "diff"], capture_output=True, text=True)
            return res.stdout
        except Exception:
            return ""

def main():
    parser = argparse.ArgumentParser(description="AI Code Reviewer Engine")
    parser.add_argument("--local", action="store_true", help="Run local review on current git diff")
    parser.add_argument("--diff", type=str, help="Path to raw patch / diff file to review")
    parser.add_argument("--config", type=str, help="Path to custom config YAML")
    args = parser.parse_args()

    config = ReviewConfig.load(args.config)
    engine = ReviewEngine(config=config)

    if args.diff:
        if os.path.exists(args.diff):
            with open(args.diff, "r", encoding="utf-8") as f:
                diff_text = f.read()
            engine.run_local_review(diff_text=diff_text)
        else:
            print(f"❌ Patch file not found: {args.diff}")
            sys.exit(1)
    elif args.local or not os.environ.get("GITHUB_EVENT_PATH"):
        engine.run_local_review()
    else:
        engine.run_github_event()

if __name__ == "__main__":
    main()
