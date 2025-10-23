"""Billing and budget management."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_config


@dataclass
class BillingEntry:
    """A single billing entry."""
    timestamp: float
    cost_usd: float
    model: str
    task_type: str


class BillingManager:
    """Manages billing ledger and budgets."""

    def __init__(self):
        config = get_config()
        self.config = config
        self.billing_file = Path.cwd() / ".cli_ai_coder" / "billing.json"
        self.entries: List[BillingEntry] = []
        self._load_billing()

    def _ensure_dir(self) -> None:
        """Ensure the billing directory exists."""
        self.billing_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_billing(self) -> None:
        """Load billing from file."""
        if not self.billing_file.exists():
            return

        try:
            with open(self.billing_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.entries = [BillingEntry(**entry) for entry in data.get("entries", [])]
        except (json.JSONDecodeError, FileNotFoundError, KeyError):
            self.entries = []

    def _save_billing(self) -> None:
        """Save billing to file."""
        self._ensure_dir()
        try:
            data = {
                "entries": [entry.__dict__ for entry in self.entries]
            }
            with open(self.billing_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except (OSError, IOError):
            pass

    def add_entry(self, cost_usd: float, model: str, task_type: str) -> None:
        """Add a billing entry."""
        if cost_usd <= 0:
            return

        entry = BillingEntry(
            timestamp=time.time(),
            cost_usd=cost_usd,
            model=model,
            task_type=task_type
        )
        self.entries.append(entry)
        self._save_billing()

    def get_monthly_cost(self, year: Optional[int] = None, month: Optional[int] = None) -> float:
        """Get total cost for the specified month (current if not specified)."""
        import calendar
        now = time.localtime()
        if year is None:
            year = now.tm_year
        if month is None:
            month = now.tm_mon

        # Get month start/end timestamps
        start_time = calendar.timegm((year, month, 1, 0, 0, 0))
        if month == 12:
            end_time = calendar.timegm((year + 1, 1, 1, 0, 0, 0))
        else:
            end_time = calendar.timegm((year, month + 1, 1, 0, 0, 0))

        return sum(
            entry.cost_usd for entry in self.entries
            if start_time <= entry.timestamp < end_time
        )

    def check_budget(self) -> Dict[str, Any]:
        """Check current budget status."""
        monthly_cost = self.get_monthly_cost()
        budget = self.config.billing_monthly_budget_usd
        soft_limit = budget * self.config.billing_soft_limit_ratio

        status = "ok"
        message = None

        if monthly_cost >= budget and self.config.billing_hard_stop:
            status = "hard_stop"
            message = f"Monthly budget of ${budget:.2f} exceeded. Blocking AI calls."
        elif monthly_cost >= soft_limit:
            status = "soft_warning"
            message = f"Monthly cost ${monthly_cost:.2f} exceeds soft limit of ${soft_limit:.2f}."

        return {
            "status": status,
            "monthly_cost": monthly_cost,
            "budget": budget,
            "soft_limit": soft_limit,
            "message": message
        }

    def reset_budget(self, year: Optional[int] = None, month: Optional[int] = None) -> None:
        """Reset budget for the specified month."""
        import calendar
        now = time.localtime()
        if year is None:
            year = now.tm_year
        if month is None:
            month = now.tm_mon

        start_time = calendar.timegm((year, month, 1, 0, 0, 0))
        if month == 12:
            end_time = calendar.timegm((year + 1, 1, 1, 0, 0, 0))
        else:
            end_time = calendar.timegm((year, month + 1, 1, 0, 0, 0))

        self.entries = [
            entry for entry in self.entries
            if not (start_time <= entry.timestamp < end_time)
        ]
        self._save_billing()

    def export_csv(self, path: str) -> None:
        """Export billing history to CSV."""
        import csv
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "cost_usd", "model", "task_type"])
            for entry in self.entries:
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp)),
                    entry.cost_usd,
                    entry.model,
                    entry.task_type
                ])


# Global instance
billing_manager = BillingManager()