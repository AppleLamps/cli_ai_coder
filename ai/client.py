"""xAI OpenAI-compatible client for AI coding assistant."""

import json
import os
import random
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI

from core.config import get_config
from core.utils import MetricsStore
from ai.context import estimate_tokens
from ai.history import history
from ai.providers.xai import XAIProvider
from ai.providers.openai import OpenAIProvider
from ai.providers.ollama import OllamaProvider


DEFAULT_SYSTEM_PROMPT = (
    "You are a precise, senior code assistant. Prefer minimal diffs, preserve style, "
    "explain tradeoffs briefly, and output patches when editing existing files."
)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for API calls."""

    def __init__(self, fail_threshold: int, window_sec: int, cooldown_sec: int):
        self.fail_threshold = fail_threshold
        self.window_sec = window_sec
        self.cooldown_sec = cooldown_sec
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.next_attempt_time = 0

    def should_attempt(self) -> bool:
        """Check if we should attempt the call."""
        now = time.time()

        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if now >= self.next_attempt_time:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        return False

    def record_success(self):
        """Record a successful call."""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED

    def record_failure(self):
        """Record a failed call."""
        now = time.time()
        self.failure_count += 1
        self.last_failure_time = now

        if self.failure_count >= self.fail_threshold:
            self.state = CircuitBreakerState.OPEN
            self.next_attempt_time = now + self.cooldown_sec

    def get_state(self) -> str:
        """Get current state as string."""
        return self.state.value


class XAIClient:
    """Client for interacting with AI models via providers."""

    def __init__(self) -> None:
        config = get_config()
        self.config = config
        self.provider_name = config.provider
        self.providers = {
            "xai": XAIProvider(),
            "openai": OpenAIProvider(),
            "ollama": OllamaProvider(),
        }
        self.provider = self._select_provider()
        self.tool_registry: Dict[str, Callable] = {}
        self.max_tool_calls = config.max_tool_calls
        self.project_root = Path.cwd()
        self.allow_tool_run_tests = config.allow_tool_run_tests
        self.metrics_store = MetricsStore(max_entries=config.metrics_window)

        # Network resilience (keep for backward compatibility, but delegate to provider if possible)
        self.max_retries = config.network_max_retries
        self.base_delay_ms = config.network_base_delay_ms
        self.backoff_multiplier = config.network_backoff_multiplier
        self.jitter_ratio = config.network_jitter_ratio
        self.request_timeout_sec = config.network_request_timeout_sec
        self.offline_mode = config.network_offline

        # Circuit breaker per model
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

    def _select_provider(self):
        """Select the best available provider."""
        provider = self.providers.get(self.provider_name)
        if provider and provider.is_available():
            return provider
        # Fallback to xAI if configured provider not available
        if self.provider_name != "xai" and self.providers["xai"].is_available():
            return self.providers["xai"]
        # Fallback to OpenAI
        if self.providers["openai"].is_available():
            return self.providers["openai"]
        # Fallback to Ollama
        if self.providers["ollama"].is_available():
            return self.providers["ollama"]
        raise Exception("No AI providers available")

    @property
    def client(self):
        """Get the provider's client, ensuring it's initialized."""
        if hasattr(self.provider, '_ensure_client'):
            self.provider._ensure_client()
        return self.provider.client

    def _get_circuit_breaker(self, model: str) -> CircuitBreaker:
        """Get or create circuit breaker for model."""
        config = get_config()
        if model not in self.circuit_breakers:
            self.circuit_breakers[model] = CircuitBreaker(
                fail_threshold=config.network_circuit_fail_threshold,
                window_sec=config.network_circuit_window_sec,
                cooldown_sec=config.network_circuit_cooldown_sec
            )
        return self.circuit_breakers[model]

    def _should_retry(self, exception: Exception) -> bool:
        """Check if exception is retryable."""
        # Retry on network errors, 429, 5xx
        if hasattr(exception, 'status_code'):
            return exception.status_code in (429, 500, 502, 503, 504)
        # Retry on connection errors
        return isinstance(exception, (ConnectionError, TimeoutError))

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with backoff and jitter."""
        delay = self.base_delay_ms * (self.backoff_multiplier ** attempt) / 1000.0
        jitter = delay * self.jitter_ratio * (random.random() * 2 - 1)
        return max(0.1, delay + jitter)

    def _retry_call(self, func, model: str, *args, **kwargs):
        """Retry a call with circuit breaker."""
        breaker = self._get_circuit_breaker(model)

        for attempt in range(self.max_retries + 1):
            if not breaker.should_attempt():
                raise Exception(f"Circuit breaker is OPEN for {model}")

            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                if attempt < self.max_retries and self._should_retry(e):
                    delay = self._calculate_delay(attempt)
                    time.sleep(delay)
                    continue
                else:
                    raise e

    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool function."""
        self.tool_registry[name] = func

    def complete_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[str], None]] = None,
        enable_tools: bool = False,
        tool_callback: Optional[Callable[[str, float], None]] = None,
        task_type: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        applied_patch: bool = False
    ) -> str:
        """
        Complete a chat with the specified model, optionally with tool calling.

        Args:
            model: The model name (e.g., 'grok-code-fast-1').
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            callback: Optional callback for streaming chunks.
            enable_tools: Whether to enable tool calling.
            tool_callback: Optional callback for tool execution.
            task_type: Optional task type for history recording.
            input_files: Optional list of input files for history.
            applied_patch: Whether a patch was applied from this interaction.

        Returns:
            The full response content if no callback, empty string if streaming.
        """
        # Check offline mode
        if self.offline_mode:
            offline_msg = "AI is in offline mode. Enable online mode to make API calls."
            if callback:
                callback(offline_msg)
            return ""

        # Check circuit breaker
        breaker = self._get_circuit_breaker(model)
        if not breaker.should_attempt():
            breaker_msg = f"Circuit breaker is OPEN for {model}. Waiting for cooldown."
            if callback:
                callback(breaker_msg)
            return ""

        if not enable_tools or not self.tool_registry:
            # Standard completion without tools
            return self._complete_standard(model, messages, temperature, max_tokens, callback, task_type, input_files, applied_patch)

        # Tool-enabled completion
        return self._complete_with_tools(model, messages, temperature, max_tokens, callback, task_type, input_files, applied_patch)
        if not enable_tools or not self.tool_registry:
            # Standard completion without tools
            return self._complete_standard(model, messages, temperature, max_tokens, callback)

        # Tool-enabled completion
        return self._complete_with_tools(model, messages, temperature, max_tokens, callback)

    def _complete_standard(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        callback: Optional[Callable[[str], None]],
        task_type: Optional[str],
        input_files: Optional[List[str]],
        applied_patch: bool
    ) -> str:
        """Standard completion without tools."""
        def _call():
            start_time = time.time()
            input_tokens = sum(estimate_tokens(msg.get('content', '')) for msg in messages)
            
            tool_calls = []  # No tools for standard completion
            
            if callback:
                # Streaming mode
                stream = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    timeout=self.request_timeout_sec
                )
                response_content = ""
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        response_content += content
                        callback(content)
                # For streaming, we don't have the full response, so estimate output tokens as 0
                elapsed_ms = int((time.time() - start_time) * 1000)
                output_tokens = estimate_tokens(response_content)
                self.metrics_store.add_completion(model, input_tokens, output_tokens, elapsed_ms)
                
                # Record history
                self._record_history(task_type, model, input_files or [], 
                                   {"input": input_tokens, "output": output_tokens}, 
                                   tool_calls, response_content, applied_patch)
                return ""
            else:
                # Non-streaming
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    timeout=self.request_timeout_sec
                )
                content = response.choices[0].message.content
                elapsed_ms = int((time.time() - start_time) * 1000)
                output_tokens = estimate_tokens(content)
                self.metrics_store.add_completion(model, input_tokens, output_tokens, elapsed_ms)
                
                # Record history
                self._record_history(task_type, model, input_files or [], 
                                   {"input": input_tokens, "output": output_tokens}, 
                                   tool_calls, content, applied_patch)
                return content

        try:
            return self._retry_call(_call, model)
        except Exception as e:
            error_msg = f"API call failed: {e}"
            if callback:
                callback(error_msg)
            return ""

    def _complete_with_tools(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        callback: Optional[Callable[[str], None]],
        task_type: Optional[str],
        input_files: Optional[List[str]],
        applied_patch: bool
    ) -> str:
        """Complete with tool calling enabled."""
        start_time = time.time()
        input_tokens = sum(estimate_tokens(msg.get('content', '')) for msg in messages)
        
        tools = self._build_tools_schema()
        tool_call_count = 0
        final_response = ""
        tool_calls = []

        while tool_call_count < self.max_tool_calls:
            # Create completion with tools
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice="auto" if tool_call_count == 0 else None
            )

            message = response.choices[0].message
            content = message.content or ""

            # Add assistant message
            assistant_message = {"role": "assistant", "content": content}
            if message.tool_calls:
                assistant_message["tool_calls"] = message.tool_calls
            messages.append(assistant_message)

            # Check for tool calls
            if not message.tool_calls:
                # No more tool calls, return final content
                final_response = content
                if callback:
                    callback(content)
                break

            # Execute tool calls
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # Security check: validate tool name
                if tool_name not in self.tool_registry:
                    tool_result = f"Error: Unknown tool '{tool_name}'"
                else:
                    try:
                        # Execute tool
                        tool_start = time.time()
                        tool_result = self.tool_registry[tool_name](**tool_args)
                        elapsed = time.time() - tool_start
                        tool_calls.append({"name": tool_name, "duration": elapsed})
                        # Redact sensitive data
                        tool_result = self._redact_tool_output(tool_result)
                        if tool_callback:
                            tool_callback(f"{tool_name}", elapsed)
                    except Exception as e:
                        tool_result = f"Error executing {tool_name}: {e}"
                        tool_calls.append({"name": tool_name, "duration": 0.0})
                        if tool_callback:
                            tool_callback(f"{tool_name}", 0.0)
                # Add tool result message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result)
                })

            tool_call_count += 1

        # Record metrics
        elapsed_ms = int((time.time() - start_time) * 1000)
        output_tokens = estimate_tokens(final_response)
        self.metrics_store.add_completion(model, input_tokens, output_tokens, elapsed_ms)
        
        # Record history
        self._record_history(task_type, model, input_files or [], 
                           {"input": input_tokens, "output": output_tokens}, 
                           tool_calls, final_response, applied_patch)
        
        return final_response

    def _build_tools_schema(self) -> List[Dict[str, Any]]:
        """Build OpenAI tools schema from registry."""
        tools = []
        for name, func in self.tool_registry.items():
            # Simple schema - could be enhanced with proper function inspection
            if name == "repo_search":
                tools.append({
                    "type": "function",
                    "function": {
                        "name": "repo_search",
                        "description": "Search project files for relevant content",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"},
                                "globs": {"type": "array", "items": {"type": "string"}, "description": "Optional file patterns"},
                                "limit": {"type": "integer", "description": "Maximum results", "default": 5}
                            },
                            "required": ["query"]
                        }
                    }
                })
            elif name == "run_tests" and self.allow_tool_run_tests:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": "run_tests",
                        "description": "Run pytest and return results",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        }
                    }
                })
            elif name == "read_file":
                tools.append({
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read file content for targeted access",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "File path relative to project root"},
                                "max_bytes": {"type": "integer", "description": "Maximum bytes to read", "default": 200000}
                            },
                            "required": ["path"]
                        }
                    }
                })
        return tools

    def _redact_tool_output(self, output: Any) -> Any:
        """Redact sensitive information from tool outputs."""
        from core.utils import redact
        config = get_config()
        patterns = getattr(config, 'redact_patterns', ["API_KEY", "SECRET", "TOKEN", "PASSWORD"])
        if isinstance(output, str):
            return redact(output, patterns)
        elif isinstance(output, dict):
            return {k: self._redact_tool_output(v) for k, v in output.items()}
        elif isinstance(output, list):
            return [self._redact_tool_output(item) for item in output]
        else:
            return output

    def _record_history(
        self,
        task_type: Optional[str],
        model: str,
        input_files: List[str],
        token_metrics: Dict[str, int],
        tool_calls: List[Dict[str, float]],
        response: str,
        applied_patch: bool
    ) -> None:
        """Record interaction in history."""
        if not task_type:
            return
        
        import hashlib
        response_hash = hashlib.sha256(response.encode('utf-8')).hexdigest()[:16] if response else None
        
        # Calculate cost
        cost_usd = self._calculate_cost(model, token_metrics)
        
        # Add to billing
        if cost_usd:
            from core.billing import billing_manager
            billing_manager.add_entry(cost_usd, model, task_type)
        
        history.add_entry(
            task_type=task_type,
            model=model,
            input_files=input_files,
            token_metrics=token_metrics,
            tool_calls=tool_calls,
            response_hash=response_hash,
            applied_patch=applied_patch,
            cost_usd=cost_usd
        )

    def _calculate_cost(self, model: str, token_metrics: Dict[str, int]) -> Optional[float]:
        """Calculate cost in USD for the completion."""
        try:
            price_table = self.provider.price_table()
            if model in price_table:
                prices = price_table[model]
                input_cost = (token_metrics.get("input", 0) / 1_000_000) * prices.get("input", 0)
                output_cost = (token_metrics.get("output", 0) / 1_000_000) * prices.get("output", 0)
                return input_cost + output_cost
        except Exception:
            pass
        return None