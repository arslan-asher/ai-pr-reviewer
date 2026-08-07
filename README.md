# 🐇 GitHub Native AI PR Review Agent (CodeRabbit Alternative)

An autonomous, 100% serverless, zero-cost AI Code Reviewer that runs entirely inside GitHub Actions. Powered by Google Gemini AI (Free Tier) and standard `secrets.GITHUB_TOKEN`.

Delivers senior-level line-by-line feedback with **1-click GitHub commit suggestions**, PR walkthrough summaries, Mermaid sequence diagrams, pre-merge safety checks, and interactive `@ai-reviewer` chat!

---

## ✨ Features (CodeRabbit Parity)

1. **🔍 Line-by-Line Code Review & 1-Click Fixes**:
   - Analyzes unified diff hunks and adds comments to the exact line in GitHub PRs.
   - Generates GitHub ` ```suggestion ` blocks allowing developers to apply fixes with a single click in GitHub's UI.
   - Includes collapsible `<details><summary>Analysis Chain</summary></details>`.

2. **📋 PR Walkthrough & Mermaid Diagrams**:
   - Executive 2-sentence summary and file changes table.
   - Auto-generated Mermaid Sequence / Architecture diagrams for component interactions.

3. **🛡️ Pre-Merge Safety & Quality Checklist**:
   - Audits for OWASP Top 10 vulnerabilities, API key/secret leaks, and SQL injections.
   - Flags $O(N^2)$ loops, N+1 query patterns, and missing validation.

4. **💬 Interactive PR Chat**:
   - Reply to any comment or type `@ai-reviewer explain [question]` to chat with the bot directly on GitHub.
   - Type `@ai-reviewer review` to re-trigger an audit.

5. **⚡ 100% Serverless & Free**:
   - Runs in GitHub Actions (`ubuntu-latest`). No servers to host or maintain.
   - Free Gemini 2.5 / 1.5 Flash API (15 requests/min & 1M tokens/min free).

---

## 🚀 2-Minute Quick Setup

### Step 1: Get a Free Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com).
2. Click **Get API Key** and create a free key.

### Step 2: Add Secret to Your GitHub Repository
1. In your GitHub repository, navigate to **Settings** -> **Secrets and variables** -> **Actions**.
2. Click **New repository secret**.
3. Name: `GEMINI_API_KEY`
4. Value: *Paste your Google Gemini API key*.

### Step 3: Copy the Workflow File
Add `.github/workflows/ai-code-review.yml` to your repository:

```yaml
name: "🤖 AI Code Reviewer"

on:
  pull_request:
    types: [opened, synchronize, reopened]
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write
  issues: write

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.event.issue.number || github.run_id }}
  cancel-in-progress: true

jobs:
  review:
    if: >
      github.event_name == 'pull_request' ||
      (github.event_name == 'issue_comment' && github.event.issue.pull_request && contains(github.event.comment.body, '@ai-reviewer')) ||
      (github.event_name == 'pull_request_review_comment' && contains(github.event.comment.body, '@ai-reviewer'))
    runs-on: ubuntu-latest
    steps:
      - name: 📥 Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: 🐍 Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 📦 Install Dependencies
        run: pip install google-generativeai requests pyyaml

      - name: 🚀 Run AI PR Reviewer
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GITHUB_EVENT_PATH: ${{ github.event_path }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_EVENT_NAME: ${{ github.event_name }}
        run: python agent/review_engine.py
```

---

## 💻 Local IDE / VS Code Preview & Testing

You can also run reviews locally in your terminal or VS Code before pushing code to GitHub!

```bash
# Review a sample patch:
python agent/review_engine.py --diff test_patch.diff

# Review your current uncommitted git diff:
python agent/review_engine.py --local
```

---

## 🌐 Visual Offline Simulator

Open `simulator/index.html` in any browser to preview the exact CodeRabbit-style GitHub UI, test diffs, inspect Mermaid diagrams, and simulate 1-click commits.
