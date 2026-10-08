"""Rule Enforcer - Tool Execute Before Extension

Validates tool calls against configurable rules before execution.
Blocks violating tool calls by raising HandledException(guidance) from the
tool_execute_before hook: the exception propagates out of the extension
dispatcher, so the tool's execute() is never reached and the guidance text
becomes the tool's error feedback to the agent.

Modes (config top-level `mode`):
- "enforce" (default): violating calls are blocked.
- "audit": nothing is blocked; would-be violations are logged with detail.
  Use this to evaluate rules safely before turning them on.

Do NOT mutate kwargs here to change tool behavior: since framework v2.13
the tool executes with its ORIGINAL arguments (upstream agent0ai/agent-zero
issue #1926) - argument mutation in this hook is silently ignored.
"""

import importlib.util
import json
import os

from helpers.errors import HandledException
from helpers.extension import Extension
from helpers.print_style import PrintStyle

_module_cache = None


def _load_rule_engine_module():
    """Import the rule engine module, tolerating non-standard install roots.

    Standard installs run from /a0, where the package import works.
    Fallback: load helpers/rule_engine.py directly relative to this file
    (extensions/python/<hook>/<file> is three directories below the plugin
    root), so the plugin also works from custom plugin directories.
    """
    global _module_cache
    if _module_cache is not None:
        return _module_cache

    try:
        from usr.plugins.rule_enforcer.helpers import rule_engine as module

        _module_cache = module
        return module
    except ImportError:
        pass

    plugin_root = os.path.abspath(__file__)
    for _ in range(3):
        plugin_root = os.path.dirname(plugin_root)

    engine_path = os.path.join(plugin_root, "helpers", "rule_engine.py")
    spec = importlib.util.spec_from_file_location(
        "rule_enforcer_rule_engine", engine_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"rule_engine.py not found at {engine_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_cache = module
    return module


def _build_guidance(violation: dict) -> str:
    rule_id = violation.get("id", "unknown")
    description = violation.get("description", "")
    guidance = violation.get(
        "block_message",
        f"RULE VIOLATION ({rule_id}): {description}",
    )
    suggested_tool = violation.get("suggested_tool", "")
    if suggested_tool:
        guidance += f"\nSuggested alternative tool: {suggested_tool}"
    return guidance


def _audit_detail(violation: dict, tool_name: str, tool_args: dict) -> str:
    return json.dumps(
        {
            "event": "rule_enforcer.audit",
            "rule": violation.get("id", "unknown"),
            "tool": tool_name,
            "args_keys": sorted(str(k) for k in tool_args.keys()),
        },
        default=str,
    )


class RuleValidator(Extension):

    async def execute(self, **kwargs):
        if not self.agent:
            return

        tool_name = kwargs.get("tool_name", "")
        tool_args = kwargs.get("tool_args") or {}

        if not tool_name or not tool_args:
            return

        try:
            engine = _load_rule_engine_module()

            # Load config fresh each call (rules + mode).
            config = engine.load_config(self.agent) or {}
            rules = engine.rules_from_config(config)
            mode = str(config.get("mode") or "enforce").lower()

            violation = engine.evaluate(rules, tool_name, tool_args) if rules else None
        except HandledException:
            raise
        except Exception as e:
            # A broken rule config must never take down the agent's tool
            # call - fail open and surface the config problem in the log.
            try:
                PrintStyle(font_color="red", padding=True).print(
                    f"Rule Enforcer: evaluation error (rule skipped): {e}"
                )
            except Exception:
                pass
            return

        if violation is None:
            return

        rule_id = violation.get("id", "unknown")

        if mode == "audit":
            try:
                PrintStyle(font_color="yellow", padding=True).print(
                    f"Rule Enforcer (audit): would block '{tool_name}' - {rule_id}"
                )
                PrintStyle(font_color="dark_gray", padding=True).print(
                    _audit_detail(violation, tool_name, tool_args)
                )
            except Exception:
                pass
            return  # audit mode never blocks

        guidance = _build_guidance(violation)

        try:
            PrintStyle(font_color="yellow", padding=True).print(
                f"Rule Enforcer: Blocked '{tool_name}' - {rule_id}"
            )
        except Exception:
            pass

        # Raising here aborts the tool call before execute() runs.
        raise HandledException(guidance)
