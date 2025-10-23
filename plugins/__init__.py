"""Plugin system for extending CLI AI Coder functionality."""

import importlib
import importlib.util
import inspect
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Callable
from dataclasses import dataclass

from core.logging import logger
from core.config import get_config
from .ipc import ipc_manager


@dataclass
class PluginInfo:
    """Information about a loaded plugin."""
    name: str
    version: str
    description: str
    author: str
    enabled: bool
    safe_mode: bool
    module_path: str


class PluginBase(ABC):
    """Base class for all plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Plugin description."""
        pass

    @property
    @abstractmethod
    def author(self) -> str:
        """Plugin author."""
        pass

    def initialize(self, plugin_manager: 'PluginManager') -> None:
        """Initialize the plugin. Called when plugin is loaded."""
        pass

    def shutdown(self) -> None:
        """Shutdown the plugin. Called when plugin is unloaded."""
        pass


class ProviderPlugin(PluginBase):
    """Plugin that provides AI model capabilities."""

    @abstractmethod
    def get_models(self) -> List[str]:
        """Return list of supported model names."""
        pass

    @abstractmethod
    def complete_chat(self, model: str, messages: List[Dict], **kwargs) -> str:
        """Complete a chat conversation."""
        pass

    @abstractmethod
    def check_available(self) -> bool:
        """Check if the provider is available."""
        pass


class ToolPlugin(PluginBase):
    """Plugin that provides tools for AI agents."""

    @abstractmethod
    def get_tools(self) -> Dict[str, Callable]:
        """Return dict of tool name -> function."""
        pass


class CommandPlugin(PluginBase):
    """Plugin that provides CLI commands."""

    @abstractmethod
    def get_commands(self) -> Dict[str, Callable]:
        """Return dict of command name -> function."""
        pass


class PluginManager:
    """Manages plugin loading, enabling, and lifecycle."""

    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        self.plugin_dirs = plugin_dirs or [
            Path(__file__).parent / "plugins",
            Path.home() / ".cli_ai_coder" / "plugins"
        ]
        self.loaded_plugins: Dict[str, PluginInfo] = {}
        self.plugin_instances: Dict[str, PluginBase] = {}
        self.safe_mode = True  # Default to safe mode
        self.sandboxed_plugins: Dict[str, bool] = {}  # Track which plugins are sandboxed

        # Create plugin directories if they don't exist
        for plugin_dir in self.plugin_dirs:
            plugin_dir.mkdir(parents=True, exist_ok=True)

    def discover_plugins(self) -> List[str]:
        """Discover available plugins in plugin directories."""
        discovered = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue

            # Look for Python files that might be plugins
            for py_file in plugin_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                module_name = py_file.stem
                discovered.append(module_name)

            # Look for plugin subdirectories with __init__.py
            for subdir in plugin_dir.iterdir():
                if subdir.is_dir() and (subdir / "__init__.py").exists():
                    module_name = subdir.name
                    discovered.append(module_name)

        return list(set(discovered))  # Remove duplicates

    def load_plugin(self, plugin_name: str, enabled: bool = True, safe_mode: Optional[bool] = None) -> bool:
        """Load a plugin by name."""
        if plugin_name in self.loaded_plugins:
            logger.warning(f"Plugin {plugin_name} already loaded")
            return True

        try:
            # Import the plugin module
            plugin_module = self._import_plugin_module(plugin_name)
            if not plugin_module:
                return False

            # Find plugin classes
            plugin_classes = self._find_plugin_classes(plugin_module)
            if not plugin_classes:
                logger.error(f"No plugin classes found in {plugin_name}")
                return False

            # Use the first plugin class found
            plugin_class = plugin_classes[0]
            plugin_instance = plugin_class()

            # Get plugin info
            info = PluginInfo(
                name=plugin_instance.name,
                version=plugin_instance.version,
                description=plugin_instance.description,
                author=plugin_instance.author,
                enabled=enabled,
                safe_mode=safe_mode if safe_mode is not None else self.safe_mode,
                module_path=plugin_module.__file__ if hasattr(plugin_module, '__file__') else str(plugin_name)
            )

            # Store plugin info and instance
            self.loaded_plugins[plugin_name] = info
            self.plugin_instances[plugin_name] = plugin_instance

            # Initialize plugin if enabled
            if enabled:
                try:
                    plugin_instance.initialize(self)
                    logger.info(f"Plugin {plugin_name} loaded and initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize plugin {plugin_name}: {e}")
                    return False
            else:
                logger.info(f"Plugin {plugin_name} loaded but disabled")

            return True

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}")
            return False

    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin."""
        if plugin_name not in self.loaded_plugins:
            logger.warning(f"Plugin {plugin_name} not loaded")
            return True

        try:
            plugin_instance = self.plugin_instances.get(plugin_name)
            if plugin_instance:
                plugin_instance.shutdown()

            del self.loaded_plugins[plugin_name]
            del self.plugin_instances[plugin_name]

            logger.info(f"Plugin {plugin_name} unloaded")
            return True

        except Exception as e:
            logger.error(f"Failed to unload plugin {plugin_name}: {e}")
            return False

    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a loaded plugin."""
        if plugin_name not in self.loaded_plugins:
            logger.error(f"Plugin {plugin_name} not loaded")
            return False

        info = self.loaded_plugins[plugin_name]
        if info.enabled:
            return True

        try:
            plugin_instance = self.plugin_instances[plugin_name]
            plugin_instance.initialize(self)
            info.enabled = True
            logger.info(f"Plugin {plugin_name} enabled")
            return True
        except Exception as e:
            logger.error(f"Failed to enable plugin {plugin_name}: {e}")
            return False

    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a loaded plugin."""
        if plugin_name not in self.loaded_plugins:
            logger.error(f"Plugin {plugin_name} not loaded")
            return False

        info = self.loaded_plugins[plugin_name]
        if not info.enabled:
            return True

        try:
            plugin_instance = self.plugin_instances[plugin_name]
            plugin_instance.shutdown()
            info.enabled = False
            logger.info(f"Plugin {plugin_name} disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable plugin {plugin_name}: {e}")
            return False

    def get_providers(self) -> Dict[str, ProviderPlugin]:
        """Get all enabled provider plugins."""
        providers = {}
        for name, instance in self.plugin_instances.items():
            info = self.loaded_plugins[name]
            if info.enabled and isinstance(instance, ProviderPlugin):
                providers[name] = instance
        return providers

    def get_tools(self) -> Dict[str, Callable]:
        """Get all tools from enabled tool plugins."""
        tools = {}
        for name, instance in self.plugin_instances.items():
            info = self.loaded_plugins[name]
            if info.enabled and isinstance(instance, ToolPlugin):
                plugin_tools = instance.get_tools()
                tools.update(plugin_tools)
        return tools

    def get_commands(self) -> Dict[str, Callable]:
        """Get all commands from enabled command plugins."""
        commands = {}
        for name, instance in self.plugin_instances.items():
            info = self.loaded_plugins[name]
            if info.enabled and isinstance(instance, CommandPlugin):
                plugin_commands = instance.get_commands()
                commands.update(plugin_commands)
        return commands

    def list_plugins(self) -> List[PluginInfo]:
        """List all loaded plugins."""
        return list(self.loaded_plugins.values())

    def _import_plugin_module(self, plugin_name: str) -> Optional[Any]:
        """Import a plugin module."""
        for plugin_dir in self.plugin_dirs:
            # Try as single file
            plugin_file = plugin_dir / f"{plugin_name}.py"
            if plugin_file.exists():
                spec = importlib.util.spec_from_file_location(plugin_name, plugin_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[plugin_name] = module
                    spec.loader.exec_module(module)
                    return module

            # Try as package
            plugin_package = plugin_dir / plugin_name
            init_file = plugin_package / "__init__.py"
            if init_file.exists():
                spec = importlib.util.spec_from_file_location(plugin_name, init_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[plugin_name] = module
                    spec.loader.exec_module(module)
                    return module

        return None

    def _find_plugin_classes(self, module: Any) -> List[Type[PluginBase]]:
        """Find plugin classes in a module."""
        plugin_classes = []

        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and
                issubclass(obj, PluginBase) and
                obj != PluginBase and
                obj != ProviderPlugin and
                obj != ToolPlugin and
                obj != CommandPlugin):
                plugin_classes.append(obj)

        return plugin_classes

    def set_safe_mode(self, enabled: bool):
        """Enable or disable safe mode for plugins."""
        self.safe_mode = enabled
        logger.info(f"Safe mode {'enabled' if enabled else 'disabled'}")

    def load_plugin_sandboxed(self, plugin_name: str, permissions: Optional[Dict[str, Any]] = None) -> bool:
        """Load a plugin in a sandboxed host process."""
        if plugin_name in self.loaded_plugins:
            logger.warning(f"Plugin {plugin_name} already loaded")
            return True

        # Get default permissions from config
        config = get_config()
        default_permissions = {
            "allowed_apis": ["read_repo", "run_tools"],
            "allowed_paths": [str(Path.cwd())],
            "timeout": 5.0
        }

        if permissions:
            default_permissions.update(permissions)

        # Start the sandboxed host
        import asyncio
        success = asyncio.run(ipc_manager.start_plugin(plugin_name, default_permissions))

        if success:
            # Create a proxy plugin info
            info = PluginInfo(
                name=plugin_name,
                version="sandboxed",
                description=f"Sandboxed plugin {plugin_name}",
                author="sandbox",
                enabled=True,
                safe_mode=True,
                module_path=f"sandbox://{plugin_name}"
            )

            self.loaded_plugins[plugin_name] = info
            self.sandboxed_plugins[plugin_name] = True
            logger.info(f"Plugin {plugin_name} loaded in sandbox")
            return True
        else:
            logger.error(f"Failed to start sandboxed plugin {plugin_name}")
            return False

    def unload_plugin_sandboxed(self, plugin_name: str) -> bool:
        """Unload a sandboxed plugin."""
        if plugin_name not in self.sandboxed_plugins:
            logger.warning(f"Plugin {plugin_name} is not sandboxed")
            return False

        import asyncio
        success = asyncio.run(ipc_manager.stop_plugin(plugin_name))

        if success:
            if plugin_name in self.loaded_plugins:
                del self.loaded_plugins[plugin_name]
            del self.sandboxed_plugins[plugin_name]
            logger.info(f"Sandboxed plugin {plugin_name} unloaded")
            return True
        else:
            logger.error(f"Failed to stop sandboxed plugin {plugin_name}")
            return False

    def call_sandboxed_plugin(self, plugin_name: str, method: str, **params) -> Any:
        """Call a method on a sandboxed plugin."""
        if plugin_name not in self.sandboxed_plugins:
            raise Exception(f"Plugin {plugin_name} is not sandboxed")

        import asyncio
        return asyncio.run(ipc_manager.call_plugin(plugin_name, method, **params))

    def get_sandboxed_plugins(self) -> List[str]:
        """Get list of sandboxed plugin names."""
        return list(self.sandboxed_plugins.keys())

    def restart_sandboxed_plugin(self, plugin_name: str) -> bool:
        """Restart a sandboxed plugin."""
        if plugin_name not in self.sandboxed_plugins:
            return False

        import asyncio
        # Stop and restart
        asyncio.run(ipc_manager.stop_plugin(plugin_name))
        info = self.loaded_plugins[plugin_name]
        # Reconstruct permissions (simplified)
        permissions = {
            "allowed_apis": ["read_repo", "run_tools"],
            "allowed_paths": [str(Path.cwd())],
            "timeout": 5.0
        }
        success = asyncio.run(ipc_manager.start_plugin(plugin_name, permissions))
        return success


# Global plugin manager instance
plugin_manager = PluginManager()