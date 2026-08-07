import os
import fnmatch
import yaml
from typing import Dict, Any, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "1.0",
    "review": {
        "line_by_line": True,
        "pr_summary": True,
        "sequence_diagram": True,
        "pre_merge_checklist": True,
        "committable_suggestions": True,
        "min_severity": "warning",  # info, warning, critical
        "bot_name": "ai-reviewer",
        "max_comments": 15,
    },
    "path_filters": {
        "exclude": [
            "**/*.lock",
            "**/package-lock.json",
            "**/yarn.lock",
            "**/pnpm-lock.yaml",
            "**/poetry.lock",
            "**/Cargo.lock",
            "**/dist/**",
            "**/build/**",
            "**/.next/**",
            "**/*.min.js",
            "**/*.min.css",
            "**/*.svg",
            "**/*.png",
            "**/*.jpg",
            "**/*.ico",
            "**/node_modules/**",
            "**/vendor/**",
            "**/.git/**",
        ]
    },
    "guidelines": {
        "security": [
            "Flag hardcoded credentials, JWT secrets, or sensitive tokens.",
            "Verify SQL queries use parameterized statements to prevent SQL Injection.",
            "Ensure user inputs rendered in HTML/React are sanitized against XSS.",
            "Check authorization and tenant boundaries on multi-tenant data routes."
        ],
        "performance": [
            "Identify nested O(N^2) loops or unindexed DB lookups inside request loops.",
            "Flag missing pagination on unbounded database queries.",
            "Warn on unmemoized heavy computations in React rendering paths."
        ],
        "clean_code": [
            "Ensure proper error handling with meaningful status codes (e.g. 404 for not found vs 400 for bad input).",
            "Verify parameter validation on public function signatures.",
            "Ensure functions follow DRY (Don't Repeat Yourself) principles."
        ]
    },
    "chat": {
        "enabled": True,
        "commands": [
            {"trigger": "@ai-reviewer review", "action": "full_review"},
            {"trigger": "@ai-reviewer summarize", "action": "summary_only"},
            {"trigger": "@ai-reviewer explain", "action": "explain"}
        ]
    }
}

class ReviewConfig:
    def __init__(self, config_data: Dict[str, Any] = None):
        self.raw_config = config_data or {}
        # Merge with defaults
        self.review = {**DEFAULT_CONFIG["review"], **self.raw_config.get("review", {})}
        self.path_filters = {**DEFAULT_CONFIG["path_filters"], **self.raw_config.get("path_filters", {})}
        self.guidelines = {**DEFAULT_CONFIG["guidelines"], **self.raw_config.get("guidelines", {})}
        self.chat = {**DEFAULT_CONFIG["chat"], **self.raw_config.get("chat", {})}

    @classmethod
    def load(cls, config_path: str = None) -> "ReviewConfig":
        candidates = [
            config_path,
            os.environ.get("REVIEWER_CONFIG_PATH"),
            ".ai-reviewer.yml",
            ".ai-reviewer.yaml",
            ".coderabbit.yaml",
            ".coderabbit.yml"
        ]
        for path in candidates:
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            return cls(data)
                except Exception as e:
                    print(f"⚠️ Warning loading config from {path}: {e}")
        return cls(DEFAULT_CONFIG)

    def is_file_excluded(self, file_path: str) -> bool:
        exclude_patterns = self.path_filters.get("exclude", [])
        clean_path = file_path.replace("\\", "/")
        for pattern in exclude_patterns:
            clean_pattern = pattern.replace("\\", "/")
            if fnmatch.fnmatch(clean_path, clean_pattern) or fnmatch.fnmatch(os.path.basename(clean_path), clean_pattern):
                return True
        return False

    @property
    def bot_name(self) -> str:
        return self.review.get("bot_name", "ai-reviewer")

    @property
    def max_comments(self) -> int:
        return self.review.get("max_comments", 15)

    @property
    def min_severity(self) -> str:
        return self.review.get("min_severity", "warning").lower()
