"""AI interaction history persistence."""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_config


@dataclass
class HistoryEntry:
    """A single AI interaction entry."""
    timestamp: float
    task_type: str
    model: str
    input_files: List[str]
    token_metrics: Dict[str, int]
    tool_calls: List[Dict[str, Any]]  # List of {"name": str, "duration": float}
    response_hash: Optional[str]  # Truncated hash of response for deduplication
    applied_patch: bool
    cost_usd: Optional[float] = None  # Cost in USD
    commits: Optional[List[str]] = None  # For plan apply, list of commit SHAs

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'HistoryEntry':
        """Create from dictionary."""
        return cls(**data)


class AIHistory:
    """Manages AI interaction history."""

    def __init__(self):
        config = get_config()
        self.enabled = config.history_enabled
        self.max_entries = config.history_max_entries
        self.history_file = Path.cwd() / ".cli_ai_coder" / "history.jsonl"
        self.entries: List[HistoryEntry] = []
        self._load_history()

    def _ensure_dir(self) -> None:
        """Ensure the history directory exists."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_history(self) -> None:
        """Load history from file."""
        if not self.enabled or not self.history_file.exists():
            return

        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        entry = HistoryEntry.from_dict(data)
                        self.entries.append(entry)
        except (json.JSONDecodeError, FileNotFoundError, KeyError):
            # If loading fails, start with empty history
            self.entries = []

    def _save_history(self) -> None:
        """Save history to file."""
        if not self.enabled:
            return

        self._ensure_dir()
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                for entry in self.entries:
                    json.dump(entry.to_dict(), f)
                    f.write('\n')
        except (OSError, IOError):
            # If saving fails, continue without error
            pass

    def add_entry(
        self,
        task_type: str,
        model: str,
        input_files: List[str],
        token_metrics: Dict[str, int],
        tool_calls: List[Dict[str, Any]],
        response_hash: Optional[str],
        applied_patch: bool,
        cost_usd: Optional[float] = None
    ) -> None:
        """Add a new history entry."""
        if not self.enabled:
            return

        entry = HistoryEntry(
            timestamp=time.time(),
            task_type=task_type,
            model=model,
            input_files=input_files,
            token_metrics=token_metrics,
            tool_calls=tool_calls,
            response_hash=response_hash,
            applied_patch=applied_patch,
            cost_usd=cost_usd
        )

        self.entries.append(entry)

        # Enforce max entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

        self._save_history()

    def add_plan_entry(self, plan_id: str, title: str, steps_count: int, commits: Optional[List[str]] = None) -> None:
        """Add a plan execution entry."""
        if not self.enabled:
            return

        # Create a synthetic entry for plan execution
        entry = HistoryEntry(
            timestamp=time.time(),
            task_type="plan_apply",
            model="planner",
            input_files=[],
            token_metrics={"input": 0, "output": 0},
            tool_calls=[],
            response_hash=plan_id,
            applied_patch=True,
            commits=commits
        )

        # Add metadata
        entry._plan_title = title
        entry._steps_count = steps_count

        self.entries.append(entry)

        # Enforce max entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

        self._save_history()

    def get_entries(self, limit: Optional[int] = None) -> List[HistoryEntry]:
        """Get history entries, most recent first."""
        entries = sorted(self.entries, key=lambda e: e.timestamp, reverse=True)
        if limit:
            entries = entries[:limit]
        return entries

    def clear_history(self) -> None:
        """Clear all history."""
        self.entries = []
        self._save_history()

    def get_stats(self) -> Dict[str, int]:
        """Get basic statistics."""
        if not self.entries:
            return {"total_entries": 0, "patches_applied": 0, "total_tokens": 0}

        patches_applied = sum(1 for e in self.entries if e.applied_patch)
        total_tokens = sum(sum(e.token_metrics.values()) for e in self.entries)

        return {
            "total_entries": len(self.entries),
            "patches_applied": patches_applied,
            "total_tokens": total_tokens
        }


# Global instance
history = AIHistory()