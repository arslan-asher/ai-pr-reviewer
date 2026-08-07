import re
from typing import List, Dict, Any, Optional

class DiffHunk:
    def __init__(self, header: str, old_start: int, old_count: int, new_start: int, new_count: int, lines: List[str]):
        self.header = header
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines = lines  # List of lines starting with ' ', '+', '-'
        self.line_mappings = self._compute_line_mappings()

    def _compute_line_mappings(self) -> List[Dict[str, Any]]:
        """Maps each line in the hunk to old_line_num, new_line_num, and line type."""
        mappings = []
        old_cur = self.old_start
        new_cur = self.new_start

        for raw_line in self.lines:
            if not raw_line:
                continue
            char = raw_line[0]
            content = raw_line[1:]

            if char == ' ':
                mappings.append({
                    "type": "context",
                    "old_line": old_cur,
                    "new_line": new_cur,
                    "content": content,
                    "raw": raw_line
                })
                old_cur += 1
                new_cur += 1
            elif char == '+':
                mappings.append({
                    "type": "addition",
                    "old_line": None,
                    "new_line": new_cur,
                    "content": content,
                    "raw": raw_line
                })
                new_cur += 1
            elif char == '-':
                mappings.append({
                    "type": "deletion",
                    "old_line": old_cur,
                    "new_line": None,
                    "content": content,
                    "raw": raw_line
                })
                old_cur += 1
            elif char == '\\':
                # e.g. \ No newline at end of file
                mappings.append({
                    "type": "meta",
                    "old_line": None,
                    "new_line": None,
                    "content": content,
                    "raw": raw_line
                })
        return mappings

    def has_new_line(self, line_num: int) -> bool:
        """Check if line_num exists as an addition or context on the new side."""
        for m in self.line_mappings:
            if m["new_line"] == line_num:
                return True
        return False

class FileDiff:
    def __init__(self, old_path: str, new_path: str, is_new: bool = False, is_deleted: bool = False, is_binary: bool = False):
        self.old_path = old_path
        self.new_path = new_path
        self.is_new = is_new
        self.is_deleted = is_deleted
        self.is_binary = is_binary
        self.hunks: List[DiffHunk] = []
        self.raw_patch: str = ""

    @property
    def filename(self) -> str:
        return self.new_path if self.new_path != "/dev/null" else self.old_path

    @property
    def added_lines_count(self) -> int:
        count = 0
        for h in self.hunks:
            count += sum(1 for m in h.line_mappings if m["type"] == "addition")
        return count

    @property
    def deleted_lines_count(self) -> int:
        count = 0
        for h in self.hunks:
            count += sum(1 for m in h.line_mappings if m["type"] == "deletion")
        return count

class DiffParser:
    HUNK_HEADER_REGEX = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$")

    @classmethod
    def parse_patch(cls, patch_text: str) -> List[FileDiff]:
        """Parses a full unified diff text into structured FileDiff and DiffHunk objects."""
        if not patch_text:
            return []

        lines = patch_text.splitlines()
        file_diffs: List[FileDiff] = []
        current_file: Optional[FileDiff] = None
        current_hunk_lines: List[str] = []
        current_hunk_meta: Optional[Dict[str, Any]] = None

        def flush_hunk():
            nonlocal current_hunk_lines, current_hunk_meta, current_file
            if current_file and current_hunk_meta:
                hunk = DiffHunk(
                    header=current_hunk_meta["header"],
                    old_start=current_hunk_meta["old_start"],
                    old_count=current_hunk_meta["old_count"],
                    new_start=current_hunk_meta["new_start"],
                    new_count=current_hunk_meta["new_count"],
                    lines=current_hunk_lines
                )
                current_file.hunks.append(hunk)
                current_hunk_lines = []
                current_hunk_meta = None

        def flush_file():
            nonlocal current_file
            flush_hunk()
            if current_file:
                file_diffs.append(current_file)
                current_file = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect new file diff header
            if line.startswith("diff --git "):
                flush_file()
                parts = line.split(" ")
                old_path = parts[2].lstrip("a/") if len(parts) > 2 else "unknown"
                new_path = parts[3].lstrip("b/") if len(parts) > 3 else "unknown"
                current_file = FileDiff(old_path=old_path, new_path=new_path)
                current_file.raw_patch += line + "\n"
                i += 1
                continue

            if current_file:
                current_file.raw_patch += line + "\n"

                if line.startswith("new file mode"):
                    current_file.is_new = True
                elif line.startswith("deleted file mode"):
                    current_file.is_deleted = True
                elif line.startswith("Binary files ") or "GIT binary patch" in line:
                    current_file.is_binary = True

                # Check for hunk header
                match = cls.HUNK_HEADER_REGEX.match(line)
                if match:
                    flush_hunk()
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) is not None else 1
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) is not None else 1

                    current_hunk_meta = {
                        "header": line,
                        "old_start": old_start,
                        "old_count": old_count,
                        "new_start": new_start,
                        "new_count": new_count
                    }
                    i += 1
                    continue

                if current_hunk_meta:
                    if line.startswith(("+", "-", " ", "\\")):
                        current_hunk_lines.append(line)
            i += 1

        flush_file()
        return file_diffs
