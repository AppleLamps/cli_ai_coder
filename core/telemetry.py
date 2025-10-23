"""Telemetry and analytics for CLI AI Coder."""

import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from core.logging import logger
from core.config import get_config


class TelemetryManager:
    """Manages telemetry data collection and transmission."""

    def __init__(self):
        self.config = get_config()
        self.enabled = self.config.telemetry_enabled
        self.user_id = self.config.telemetry_user_id or self._generate_user_id()
        self.data_dir = Path.home() / ".cli_ai_coder" / "telemetry"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _generate_user_id(self) -> str:
        """Generate a unique user ID."""
        return str(uuid.uuid4())

    def track_event(self, event_name: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Track a telemetry event."""
        if not self.enabled:
            return

        try:
            event = {
                "user_id": self.user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "event": event_name,
                "properties": properties or {},
                "version": "0.1.0"
            }

            # Store event locally for batch transmission
            self._store_event(event)

        except Exception as e:
            logger.error(f"Failed to track telemetry event: {e}")

    def track_command(self, command: str, duration_ms: float, success: bool) -> None:
        """Track command execution."""
        self.track_event("command_executed", {
            "command": command,
            "duration_ms": duration_ms,
            "success": success
        })

    def track_ai_request(self, model: str, tokens: int, provider: str) -> None:
        """Track AI API usage."""
        self.track_event("ai_request", {
            "model": model,
            "tokens": tokens,
            "provider": provider
        })

    def track_error(self, error_type: str, error_message: str, context: Optional[Dict] = None) -> None:
        """Track application errors."""
        self.track_event("error_occurred", {
            "error_type": error_type,
            "error_message": error_message[:500],  # Truncate long messages
            "context": context or {}
        })

    def track_feature_usage(self, feature: str, context: Optional[Dict] = None) -> None:
        """Track feature usage."""
        self.track_event("feature_used", {
            "feature": feature,
            "context": context or {}
        })

    def _store_event(self, event: Dict) -> None:
        """Store event data locally."""
        try:
            events_file = self.data_dir / "events.jsonl"

            with open(events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')

        except Exception as e:
            logger.error(f"Failed to store telemetry event: {e}")

    def get_pending_events(self) -> list:
        """Get pending events for transmission."""
        try:
            events_file = self.data_dir / "events.jsonl"
            if not events_file.exists():
                return []

            events = []
            with open(events_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))

            return events

        except Exception as e:
            logger.error(f"Failed to read pending events: {e}")
            return []

    def clear_pending_events(self) -> None:
        """Clear pending events after successful transmission."""
        try:
            events_file = self.data_dir / "events.jsonl"
            if events_file.exists():
                events_file.unlink()
        except Exception as e:
            logger.error(f"Failed to clear pending events: {e}")

    def transmit_events(self) -> bool:
        """Transmit pending events to telemetry service."""
        if not self.enabled:
            return True

        try:
            events = self.get_pending_events()
            if not events:
                return True

            # TODO: Implement actual transmission to telemetry service
            # For now, just log the events
            logger.info(f"Would transmit {len(events)} telemetry events")

            # In a real implementation, this would send to a telemetry endpoint
            # with proper error handling, retries, and privacy compliance

            self.clear_pending_events()
            return True

        except Exception as e:
            logger.error(f"Failed to transmit telemetry events: {e}")
            return False

    def enable(self) -> None:
        """Enable telemetry."""
        self.enabled = True
        logger.info("Telemetry enabled")

    def disable(self) -> None:
        """Disable telemetry."""
        self.enabled = False
        logger.info("Telemetry disabled")


# Global telemetry manager instance
telemetry = TelemetryManager()