"""Pure Python pattern matching engine for rule_enforcer plugin.

Evaluates tool calls against configurable rules using regex patterns.
Rules use AND logic within conditions, OR logic across conditions.
"""

import re
from typing import Any

PLUGIN_NAME = "rule_enforcer"


def load_rules(agent: Any) -> list[dict]:
    """Load enabled rules from plugin config via get_plugin_config."""
    from helpers.plugins import get_plugin_config

    config = get_plugin_config(PLUGIN_NAME, agent=agent) or {}
    rules = config.get("rules", [])

    enabled = [r for r in rules if r.get("enabled", True)]

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    enabled.sort(key=lambda r: priority_order.get(r.get("priority", "medium"), 2))

    return enabled


def extract_paths_from_args(tool_args: dict) -> list[str]:
    """Extract all path-like values from tool arguments."""
    paths = []

    def _extract(value: Any) -> None:
        if isinstance(value, str):
            if value:
                paths.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                _extract(v)
        elif isinstance(value, list):
            for item in value:
                _extract(item)

    if isinstance(tool_args, dict):
        for v in tool_args.values():
            _extract(v)

    return paths


def check_condition(condition: dict, tool_name: str, tool_args: dict) -> bool:
    """Check a single condition against a tool call (AND logic)."""
    cond_tool = condition.get("tool_name", "")
    if cond_tool and cond_tool != tool_name:
        return False

    paths = extract_paths_from_args(tool_args)

    has_path_pattern = bool(condition.get("path_pattern"))
    has_exclude = bool(condition.get("exclude_path_pattern"))
    has_args_check = bool(condition.get("args_check"))

    if has_path_pattern or has_exclude:
        if not paths:
            return False

        path_pattern = condition.get("path_pattern", "")
        exclude_pattern = condition.get("exclude_path_pattern", "")

        include_match = False
        if path_pattern:
            for path in paths:
                if re.search(path_pattern, path, re.IGNORECASE):
                    include_match = True
                    break
            if not include_match:
                return False

        if exclude_pattern:
            included_paths = [
                p for p in paths
                if path_pattern and re.search(path_pattern, p, re.IGNORECASE)
            ]
            non_excluded = [
                p for p in included_paths
                if not (exclude_pattern and re.search(exclude_pattern, p, re.IGNORECASE))
            ]
            if not non_excluded:
                return False

    if has_args_check:
        args_check = condition.get("args_check", {})
        for arg_key, arg_pattern in args_check.items():
            arg_value = tool_args.get(arg_key, "")
            if not isinstance(arg_value, str):
                arg_value = str(arg_value) if arg_value else ""
            if not re.search(arg_pattern, arg_value, re.IGNORECASE):
                return False

    return True


def check_rule(rule: dict, tool_name: str, tool_args: dict) -> bool:
    """Check if a rule is violated (any condition matches = violation)."""
    conditions = rule.get("conditions", [])
    for condition in conditions:
        if check_condition(condition, tool_name, tool_args):
            return True
    return False


def evaluate(rules: list[dict], tool_name: str, tool_args: dict) -> dict | None:
    """Evaluate all rules against a tool call."""
    for rule in rules:
        if check_rule(rule, tool_name, tool_args):
            return rule
    return None
