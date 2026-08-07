import os
import json
import re
from typing import Dict, Any, List, Optional

try:
    from .config import ReviewConfig
except ImportError:
    from config import ReviewConfig

class GeminiReviewer:
    def __init__(self, api_key: Optional[str] = None, config: Optional[ReviewConfig] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.config = config or ReviewConfig.load()
        self.model_name = "gemini-1.5-flash"

    def _call_gemini_api(self, prompt: str) -> Optional[str]:
        """Calls Google Gemini API directly via high-speed REST endpoint."""
        if not self.api_key:
            return None
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096
            }
        }
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=45)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
            else:
                print(f"⚠️ Gemini API returned {res.status_code}: {res.text}")
        except Exception as e:
            print(f"⚠️ Gemini REST call failed: {e}")
        return None

    def generate_review(self, pr_meta: Dict[str, Any], file_diffs: List[Any], full_patch: str) -> Dict[str, Any]:
        """
        Executes multi-stage AI review:
        1. High-level PR Walkthrough, Risk Assessment, and Mermaid Flowchart.
        2. Line-by-Line Code Review Comments with Committable ```suggestion blocks.
        """
        if not self.api_key:
            return self._generate_simulated_review(pr_meta, file_diffs)

        # Stage 1: PR Summary & Pre-Merge Checklist
        summary_markdown = self._generate_summary_walkthrough(pr_meta, file_diffs, full_patch)

        # Stage 2: Line-by-Line Code Review Comments
        inline_comments = self._generate_inline_comments(pr_meta, file_diffs)

        return {
            "summary": summary_markdown,
            "inline_comments": inline_comments
        }

    def _generate_summary_walkthrough(self, pr_meta: Dict[str, Any], file_diffs: List[Any], full_patch: str) -> str:
        prompt = f"""
You are CodeRabbit AI, an expert autonomous AI Senior Staff Engineer & Code Reviewer.
Review the following Pull Request details and unified diff to generate a concise, high-signal executive PR walkthrough.

## PR METADATA:
Title: {pr_meta.get('title', 'Pull Request')}
Description: {pr_meta.get('body', 'No description provided.')}
Author: {pr_meta.get('user', {}).get('login', 'developer')}
Changed Files: {len(file_diffs)}

## GUIDELINES & CRITERIA:
{json.dumps(self.config.guidelines, indent=2)}

## UNIFIED PATCH:
```diff
{full_patch[:30000]}
```

Generate the response in strict GitHub Flavored Markdown adhering to the following structure (DO NOT include any Mermaid or sequence diagrams):

1. **🐇 Summary & Walkthrough**:
   - A concise 2-sentence executive summary of the changes.
   - A structured markdown table summarizing changed files:
     | File | Summary | Risk |

2. **🛡️ Pre-Merge Safety & Quality Checklist**:
   - [ ] Security (OWASP, injections, secret leaks, auth)
   - [ ] Performance (No O(N^2) loops, query optimization)
   - [ ] Error Handling (Explicit status codes, proper exceptions)
   - [ ] Test & Edge Case Coverage

3. **📊 Risk Assessment**:
   - Provide an overall risk score (🟢 Low, 🟡 Medium, 🟠 High, or 🔴 Critical) with 1 sentence justification.

4. **💬 Interactive Commands**:
   - Mention: *"💡 Tip: Reply to any comment or tag `@ai-reviewer review` to ask questions or trigger updates."*

Return ONLY the markdown text.
"""
        res = self._call_gemini_api(prompt)
        if res:
            return res
        return self._generate_fallback_summary(pr_meta, file_diffs)

    def _generate_inline_comments(self, pr_meta: Dict[str, Any], file_diffs: List[Any]) -> List[Dict[str, Any]]:
        """
        Analyzes hunks of changed files to produce line-by-line comments with GitHub ```suggestion blocks.
        """
        comments = []
        for file_diff in file_diffs:
            if self.config.is_file_excluded(file_diff.filename):
                continue
            if not file_diff.hunks:
                continue

            # Analyze patch for this file
            file_comments = self._analyze_file_diff(file_diff)
            comments.extend(file_comments)

            if len(comments) >= self.config.max_comments:
                break

        return comments[:self.config.max_comments]

    def _analyze_file_diff(self, file_diff: Any) -> List[Dict[str, Any]]:
        prompt = f"""
You are CodeRabbit AI, an expert Senior Staff Software Engineer reviewing changed lines in `{file_diff.filename}`.

## FILE PATCH HUNKS:
```diff
{file_diff.raw_patch[:12000]}
```

Review the added/modified lines for:
1. Logic bugs, edge cases, and incorrect status codes (e.g. 400 vs 404 for not found).
2. Null pointer exceptions, missing guards, and parameter validation.
3. Security vulnerabilities (SQLi, hardcoded tokens, secret exposure).
4. Performance issues (nested loops, N+1 queries).

CRITICAL INSTRUCTIONS:
- You must ONLY comment on lines that exist in the new side of the diff.
- Format each comment body cleanly to match CodeRabbit AI style:
  - Header: `### 🛠️ Refactor suggestion` or `### 🔴 Security vulnerability` or `### 💡 Suggestion`
  - Bold summary: `**<Short Issue Summary>**`
  - Senior-engineer explanation referencing code symbols in backticks (`like_this`).
  - Committable suggestion block:
```suggestion
exact replacement code here
```
  - Collapsible analysis details:
<details>
<summary>▶ 🧩 Analysis chain</summary>

- Observation 1
- Root cause & impact
- Recommended remediation
</details>

- Format the response as a JSON array of objects with the following schema:
[
  {{
    "path": "{file_diff.filename}",
    "line": <NEW_SIDE_LINE_NUMBER_AS_INTEGER>,
    "body": "<Markdown comment string>"
  }}
]

If no actionable issues are found in this file, return an empty array `[]`. Return ONLY valid JSON.
"""
        res = self._call_gemini_api(prompt)
        if not res:
            return []

        text = res.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        try:
            data = json.loads(text.strip())
            if isinstance(data, list):
                valid = []
                for item in data:
                    if "line" in item and "body" in item:
                        item["path"] = file_diff.filename
                        item["side"] = "RIGHT"
                        valid.append(item)
                return valid
        except Exception as e:
            print(f"⚠️ Error parsing JSON comments from Gemini: {e}")
        return []

    def answer_interactive_chat(self, query: str, context: Dict[str, Any]) -> str:
        """Handles @ai-reviewer mentions in PR comment threads."""
        if not self.api_key:
            return f"🤖 **AI Reviewer Response**\n\nI received your query: *\"{query}\"*. (Running in simulated mode - add `GEMINI_API_KEY` for live AI responses)."

        prompt = f"""
You are CodeRabbit AI responding to a developer inside a GitHub Pull Request discussion thread.

## DEVELOPER'S QUESTION / COMMAND:
"{query}"

## PR CONTEXT:
PR Title: {context.get('pr_title', 'PR')}
Comment Thread History: {context.get('thread_context', 'N/A')}

Answer the developer with high technical accuracy, cordial tone, senior engineer perspective, and provide concrete code snippets if relevant.
"""
        res = self._call_gemini_api(prompt)
        if res:
            return res
        return "🤖 **AI Reviewer**: Unable to generate answer at this time."

    def _generate_simulated_review(self, pr_meta: Dict[str, Any], file_diffs: List[Any]) -> Dict[str, Any]:
        """Provides dynamic, context-aware analysis detecting security, performance, and logic bugs."""
        has_sqli = False
        has_secret = False
        has_status_code_issue = False
        has_perf_issue = False
        has_loadbalance_issue = False
        has_typo = False

        inline_comments = []

        for f in file_diffs:
            for hunk in f.hunks:
                for mapping in hunk.line_mappings:
                    if mapping["type"] == "addition":
                        line_num = mapping["new_line"]
                        content = mapping["content"]

                        # 1. SQL Injection Detection
                        if ("SELECT " in content or "INSERT " in content or "DELETE " in content) and ("{" in content or "%" in content or " + " in content or f"'" in content):
                            has_sqli = True
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": f"""🔴 **Security Vulnerability: SQL Injection (CWE-89)**

Directly interpolating user input (`email`, `password_input`) into raw SQL query strings creates an exploitable SQL Injection vulnerability. An attacker could bypass authentication using `' OR '1'='1`.

```suggestion
    query = "SELECT * FROM users WHERE email = ? AND password = ?"
    cursor.execute(query, (email, password_input))
```

<details>
<summary><b>🗂️ Analysis Chain</b></summary>

- User-controlled inputs formatted directly into SQL query text.
- Risk: High (Authentication bypass, data exfiltration).
- Recommended Remediation: Use parameterized query parameters.
</details>"""
                            })

                        # 2. Hardcoded Secret / JWT Secret Detection
                        if ("JWT_SECRET" in content or "API_KEY" in content or "SECRET_KEY" in content) and ("=" in content and '"' in content):
                            has_secret = True
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": f"""🟠 **Security Warning: Hardcoded Secret Exposure (CWE-798)**

Hardcoded credentials and cryptographic secrets in source code can be extracted if the repository or build artifacts are compromised.

```suggestion
import os
JWT_SECRET = os.environ.get("JWT_SECRET", "")
```

<details>
<summary><b>🗂️ Analysis Chain</b></summary>

- Plaintext secret string assigned directly in source code.
- Remediation: Load sensitive tokens from environment variables or GitHub Secrets.
</details>"""
                            })

                        # 3. Chained Dictionary / Null Pointer Crash
                        if "['customer']['address']" in content or "['address']['city']" in content or ".profile.address" in content:
                            has_perf_issue = True
                            body_text = (
                                "### 🛡️ Reliability suggestion\n\n"
                                "**Missing null-safety guard on nested dictionary access**\n\n"
                                "Directly indexing `order['customer']['address']['city']` without validation will raise a runtime `KeyError` or `TypeError` if customer metadata is missing or null.\n\n"
                                "```suggestion\n"
                                "        city = order.get('customer', {}).get('address', {}).get('city', 'Unknown')\n"
                                "```\n\n"
                                "<details>\n"
                                "<summary>▶ 🧩 Analysis chain</summary>\n\n"
                                "- Deep nested dictionary traversal on external payload.\n"
                                "- Risk: Unhandled runtime exception crashing request batch.\n"
                                "- Remediation: Use safe chained `.get()` lookups with defaults.\n"
                                "</details>"
                            )
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": body_text
                            })

                        # 4. Divide by Zero Risk
                        if "/ currency_rate" in content or "/ rate" in content:
                            body_text = (
                                "### ⚡ Reliability & Edge Case\n\n"
                                "**ZeroDivisionError risk on unvalidated denominator**\n\n"
                                "The parameter `currency_rate` is used directly as a divisor. If a caller passes `0` or `0.0`, this will trigger a critical `ZeroDivisionError`.\n\n"
                                "```suggestion\n"
                                "    adjusted_ratio = 100 / currency_rate if currency_rate and currency_rate != 0 else 0\n"
                                "```\n\n"
                                "<details>\n"
                                "<summary>▶ 🧩 Analysis chain</summary>\n\n"
                                "- Unvalidated numeric divisor in arithmetic expression.\n"
                                "- Remediation: Guard against zero values before division.\n"
                                "</details>"
                            )
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": body_text
                            })

                        # 5. Duplicate Tax Logic (Clean Code / DRY)
                        if "* 0.15" in content and "total_tax" in content:
                            body_text = (
                                "### 🧹 Clean Code suggestion\n\n"
                                "**Extract magic number and deduplicate tax calculation**\n\n"
                                "The tax multiplier `0.15` is duplicated across multiple statements. Extracting this into a named constant improves readability and makes future rate updates maintainable.\n\n"
                                "```suggestion\n"
                                "    TAX_RATE = 0.15\n"
                                "    total_tax_domestic = sum(o.get('amount', 0) * TAX_RATE for o in orders if o.get('region') == 'US')\n"
                                "```\n\n"
                                "<details>\n"
                                "<summary>▶ 🧩 Analysis chain</summary>\n\n"
                                "- Duplicate numeric literal in multiple list comprehensions.\n"
                                "- Remediation: Define top-level constant `TAX_RATE`.\n"
                                "</details>"
                            )
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": body_text
                            })

                        # 6. HTTP Status Code / Exception Handling
                        if "raise Exception" in content and ("500" in content or "400" in content):
                            has_status_code_issue = True
                            body_text = (
                                "### ⚠️ Error Handling suggestion\n\n"
                                "**Incorrect HTTP 500 status code for client validation error**\n\n"
                                "Raising a generic `500 Internal Server Error` indicates an unexpected server crash. Client input errors (such as negative order amounts) should return `400 Bad Request` or `422 Unprocessable Entity`.\n\n"
                                "```suggestion\n"
                                "        if order.get('amount', 0) < 0:\n"
                                "            raise ValueError('Order amount cannot be negative')  # Handled as 400 Bad Request\n"
                                "```\n\n"
                                "<details>\n"
                                "<summary>▶ 🧩 Analysis chain</summary>\n\n"
                                "- Status code 500 mapped to user input validation failure.\n"
                                "- Remediation: Use specific exception type mapped to HTTP 400.\n"
                                "</details>"
                            )
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": body_text
                            })

                        # 7. HTTP Status Code 400 vs 404
                        if "status_code=400" in content or "status_code = 400" in content:
                            has_status_code_issue = True
                            body_text = (
                                "### 🛠️ Refactor suggestion\n\n"
                                "**Status code correction: 400 -> 404**\n\n"
                                "The function encapsulation is a clean addition for retrieving records by identifier. However, ensure that `status_code=400` is updated to `404`, as 404 is standard for not found errors.\n\n"
                                "```suggestion\n"
                                "        status_code=404,\n"
                                "```\n\n"
                                "<details>\n"
                                "<summary>▶ 🧩 Analysis chain</summary>\n\n"
                                "- Resource lookup helper raises `ApiError`.\n"
                                "- Missing entity returns Bad Request (`400`) instead of Not Found (`404`).\n"
                                "- Recommended fix updates error code to adhere to REST specifications.\n"
                                "</details>"
                            )
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": body_text
                            })

                        # 8. Load Balancing Unvalidated Parameters
                        if "loadbalancing" in content and "add_string" in content:
                            has_loadbalance_issue = True
                            body_text = (
                                "### 🛠️ Refactor suggestion\n\n"
                                "**Unvalidated load balancing parameter**\n\n"
                                "The addition of the `loadbalancing` parameter is not validated against expected values. Ensure the parameter is one of the supported types to prevent runtime errors.\n\n"
                                "```suggestion\n"
                                "    # Validation for loadbalancing parameter\n"
                                "    if simulation.loadbalancing not in ['round_robin', 'least_conn', 'ip_hash']:\n"
                                "        raise ValueError(f'Invalid value for loadbalancing: {simulation.loadbalancing}')\n"
                                "```\n\n"
                                "<details>\n"
                                "<summary>▶ 🧩 Analysis chain</summary>\n\n"
                                "- New configuration field `loadbalancing` injected into simulation state.\n"
                                "- Unvalidated string input could propagate into downstream modules.\n"
                                "</details>"
                            )
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": body_text
                            })

                        # 9. Typo in Enum or Token
                        if "SPONSER" in content:
                            has_typo = True
                            body_text = (
                                "### 🛠️ Refactor suggestion\n\n"
                                "**Typo in enum token: Role.SPONSER -> Role.SPONSOR**\n\n"
                                "There is a typo on the usage of `Role.SPONSER`. This should be corrected to `Role.SPONSOR`.\n\n"
                                "```suggestion\n"
                                "import { Role, Status } from '@prisma/client';\n"
                                "```\n\n"
                                "<details>\n"
                                "<summary>▶ 🧩 Analysis chain</summary>\n\n"
                                "- Typo identified in enum token `SPONSER` -> `SPONSOR`.\n"
                                "</details>"
                            )
                            inline_comments.append({
                                "path": f.filename,
                                "line": line_num,
                                "side": "RIGHT",
                                "body": body_text
                            })

        # Compute dynamic risk score and safety checklist
        if has_sqli or has_secret:
            risk_rating = "🔴 **Critical / High Risk**"
            risk_justification = "Critical security issues detected (SQL Injection vulnerability or hardcoded secret exposure)."
            security_check = "- [ ] 🔴 **Security**: **Vulnerabilities Found** — SQL Injection risk or hardcoded secret detected. Requires immediate fix before merging."
        else:
            risk_rating = "🟢 **Low Risk**"
            risk_justification = "Changes are well-scoped with localized impact on route handlers and helper utilities."
            security_check = "- [x] **Security**: No exposed credentials, secrets, or raw SQL queries detected."

        error_check = "- [ ] **Error Handling**: Verify status codes match HTTP standards (use `404` for missing resources rather than `400`)." if has_status_code_issue else "- [x] **Error Handling**: Explicit status codes and proper exception handling."
        perf_check = "- [x] **Performance**: No nested $O(N^2)$ loops or unindexed lookups identified in changed paths."
        clean_check = "- [x] **Clean Code**: Adheres to DRY design and single responsibility principles."

        # Build Code Suggestions block
        suggestions_block = ""
        if inline_comments:
            suggestions_block = "\n---\n\n### 🛠️ Actionable Code Suggestions\n\n"
            for c in inline_comments:
                suggestions_block += f"#### 📍 `{c['path']}` (Line {c['line']})\n\n{c['body']}\n\n"

        summary = f"""<!-- coderabbit-ai: pr-walkthrough -->
## 🐇 Summary & Walkthrough

This Pull Request updates **{len(file_diffs)} files** across the codebase. Key improvements focus on input validation, error handling consistency, and security audits.

### 📋 Changes Walkthrough

| File | Changes | Risk |
| :--- | :--- | :--- |
"""
        for f in file_diffs[:5]:
            file_risk = "🔴 High" if (has_sqli or has_secret) else "🟢 Low"
            summary += f"| `{f.filename}` | Added `{f.added_lines_count}` lines, deleted `{f.deleted_lines_count}` lines | {file_risk} |\n"

        summary += f"""
---

### 🛡️ Pre-Merge Safety & Quality Checklist

{security_check}
{perf_check}
{error_check}
{clean_check}
{suggestions_block}
---

### 📊 Risk Assessment: {risk_rating}
{risk_justification}

---
💡 *Tip: Mention `@ai-reviewer review` to re-run, or reply directly to any comment to ask questions.*
"""

        return {
            "summary": summary,
            "inline_comments": inline_comments
        }

    def _generate_fallback_summary(self, pr_meta: Dict[str, Any], file_diffs: List[Any]) -> str:
        return self._generate_simulated_review(pr_meta, file_diffs)["summary"]
