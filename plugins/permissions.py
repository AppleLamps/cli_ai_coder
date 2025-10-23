"""Plugin permissions and security model."""

from pathlib import Path
from typing import Dict, List, Any, Set
import logging

logger = logging.getLogger(__name__)


class PluginPermissions:
    """Manages plugin permissions and security checks."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.allowed_apis: Set[str] = set(config.get("allowed_apis", []))
        self.denied_apis: Set[str] = set(config.get("denied_apis", []))
        self.allowed_paths: List[Path] = [Path(p) for p in config.get("allowed_paths", [])]
        self.denied_paths: List[Path] = [Path(p) for p in config.get("denied_paths", [])]
        self.timeout: float = config.get("timeout", 5.0)
        self.memory_limit_mb: int = config.get("memory_limit_mb", 100)

    def can_call_api(self, api_name: str) -> bool:
        """Check if an API call is allowed."""
        if api_name in self.denied_apis:
            return False

        if self.allowed_apis and api_name not in self.allowed_apis:
            return False

        return True

    def can_access_path(self, path: str) -> bool:
        """Check if a file path is accessible."""
        try:
            path_obj = Path(path).resolve()

            # Check denied paths first
            for denied_path in self.denied_paths:
                if path_obj.is_relative_to(denied_path):
                    return False

            # Check allowed paths
            if self.allowed_paths:
                for allowed_path in self.allowed_paths:
                    if path_obj.is_relative_to(allowed_path):
                        return True
                return False  # No allowed path matched

            return True  # No restrictions

        except Exception as e:
            logger.warning(f"Error checking path access for {path}: {e}")
            return False

    def get_timeout(self) -> float:
        """Get the timeout for operations."""
        return self.timeout

    def get_memory_limit(self) -> int:
        """Get the memory limit in MB."""
        return self.memory_limit_mb


def get_default_permissions(safe_mode: bool = True) -> Dict[str, Any]:
    """Get default permissions based on safe mode."""
    if safe_mode:
        return {
            "allowed_apis": [
                "read_repo",
                "run_tools",
                "search_code",
                "get_file_info"
            ],
            "denied_apis": [
                "write_file",
                "delete_file",
                "run_shell",
                "network_request"
            ],
            "allowed_paths": ["."],  # Current directory only
            "denied_paths": [],
            "timeout": 5.0,
            "memory_limit_mb": 50
        }
    else:
        # Less restrictive for non-safe mode
        return {
            "allowed_apis": [
                "read_repo",
                "run_tools",
                "search_code",
                "get_file_info",
                "write_file",
                "run_shell"
            ],
            "denied_apis": [
                "network_request",
                "system_admin"
            ],
            "allowed_paths": ["."],
            "denied_paths": ["/etc", "/usr", "C:\\Windows"],
            "timeout": 10.0,
            "memory_limit_mb": 200
        }


def validate_permissions(permissions: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize permissions configuration."""
    validated = permissions.copy()

    # Ensure required fields
    validated.setdefault("allowed_apis", [])
    validated.setdefault("denied_apis", [])
    validated.setdefault("allowed_paths", [])
    validated.setdefault("denied_paths", [])
    validated.setdefault("timeout", 5.0)
    validated.setdefault("memory_limit_mb", 100)

    # Convert path strings to Path objects for validation
    try:
        validated["allowed_paths"] = [str(Path(p).resolve()) for p in validated["allowed_paths"]]
        validated["denied_paths"] = [str(Path(p).resolve()) for p in validated["denied_paths"]]
    except Exception as e:
        logger.warning(f"Error resolving paths in permissions: {e}")

    # Validate timeout
    if not isinstance(validated["timeout"], (int, float)) or validated["timeout"] <= 0:
        validated["timeout"] = 5.0

    # Validate memory limit
    if not isinstance(validated["memory_limit_mb"], int) or validated["memory_limit_mb"] <= 0:
        validated["memory_limit_mb"] = 100

    return validated