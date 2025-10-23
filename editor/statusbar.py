"""Status bar component."""

from typing import Optional

from prompt_toolkit.layout.controls import FormattedTextControl

from core.config import get_config


class StatusBar:
    """Status bar with metrics display."""

    def __init__(self):
        self.control = FormattedTextControl(text=self._format_status())
        self.current_message = "Ready"
        self.index_status = "IDX ready"

    def set_message(self, message: str):
        """Set the current status message."""
        self.current_message = message
        self.control.text = self._format_status()

    def set_index_status(self, status: str):
        """Set the index status."""
        self.index_status = status
        self.control.text = self._format_status()

    def update_metrics(self):
        """Update the metrics display."""
        self.control.text = self._format_status()

    def _format_status(self) -> str:
        """Format the status bar text."""
        config = get_config()
        
        # Get provider info
        from ai.client import XAIClient
        client = XAIClient()
        provider_name = client.provider_name if hasattr(client, 'provider_name') else 'xai'
        current_provider = client.provider.name if hasattr(client, 'provider') else 'xai'
        
        # Get budget status
        from core.billing import billing_manager
        budget_info = billing_manager.check_budget()
        
        status_parts = [self.index_status]
        
        if config.show_metrics:
            latest_metric = client.metrics_store.get_latest()
            if latest_metric:
                # Get cost for this metric if available
                # For now, show latest cost from history
                from ai.history import history
                recent_entries = history.get_entries(limit=1)
                cost_str = ""
                if recent_entries and recent_entries[0].cost_usd:
                    cost_str = f" | ${recent_entries[0].cost_usd:.4f}"
                
                status_parts.append(f"{current_provider} @ {latest_metric.model}")
                status_parts.append(f"in:{latest_metric.input_tokens:,} out:{latest_metric.output_tokens:,}{cost_str}")
                status_parts.append(f"{latest_metric.elapsed_ms}ms")
        
        status_parts.append(self.current_message)
        
        # Add budget warning if needed
        if budget_info["status"] in ["soft_warning", "hard_stop"]:
            status_parts.append(f"⚠️ {budget_info['message']}")
        
        return " | ".join(status_parts)