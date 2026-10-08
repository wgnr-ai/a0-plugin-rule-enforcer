"""Rule Enforcer - Tool Execute Before Extension

Validates tool calls against configurable rules before execution.
Blocks violating tool calls by raising HandledException(guidance) from the
tool_execute_before hook: the exception propagates out of the extension
dispatcher, so the tool's execute() is never reached and the guidance text
becomes the tool's error feedback to the agent.

Do NOT mutate kwargs here to change tool behavior: since framework v2.13
the tool executes with its ORIGINAL arguments (upstream agent0ai/agent-zero
issue #1926) - argument mutation in this hook is silently ignored.
"""

import importlib.util
import os

from helpers.errors import HandledException
from helpers.extension import Extension
from helpers.print_style import PrintStyle


def _load_rule_engine():
    """Import the rule engine, tolerating non-standard install roots.

    Standard installs run from /a0, where the package import works.
    Fallback: load helpers/rule_engine.py directly relative to this file
    (extensions/python/<hook>/<file> is three directories below the plugin
    root), so the plugin also works from custom plugin directories.
    """
    try:
        from usr.plugins.rule_enforcer.helpers.rule_engine import (
            evaluate,
            load_rules,
        )

        return evaluate, load_rules
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
    return module.evaluate, module.load_rules


class RuleValidator(Extension):

    async def execute(self, **kwargs):
        if not self.agent:
            return

        tool_name = kwargs.get("tool_name", "")
        tool_args = kwargs.get("tool_args") or {}

        if not tool_name or not tool_args:
            return

        try:
            evaluate, load_rules = _load_rule_engine()

            # Load rules fresh from config each call
            rules = load_rules(self.agent)
            if not rules:
                return

            violation = evaluate(rules, tool_name, tool_args)
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
        description = violation.get("description", "")
        block_message = violation.get(
            "block_message",
            f"RULE VIOLATION ({rule_id}): {description}",
        )
        suggested_tool = violation.get("suggested_tool", "")

        guidance = block_message
        if suggested_tool:
            guidance += f"\nSuggested alternative tool: {suggested_tool}"

        try:
            PrintStyle(font_color="yellow", padding=True).print(
                f"Rule Enforcer: Blocked '{tool_name}' - {rule_id}"
            )
        except Exception:
            pass

        # Raising here aborts the tool call before execute() runs.
        raise HandledException(guidance)
