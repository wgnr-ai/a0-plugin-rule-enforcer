"""Rule Enforcer - Tool Execute Before Extension

Validates tool calls against configurable rules before execution.
Blocks tool calls that violate rules and returns corrective guidance.
"""

from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers.errors import HandledException


class RuleValidator(Extension):

    async def execute(self, **kwargs):
        if not self.agent:
            return

        tool_name = kwargs.get("tool_name", "")
        tool_args = kwargs.get("tool_args", {})

        if not tool_name or not tool_args:
            return

        # Import rule engine from plugin helpers
        from usr.plugins.rule_enforcer.helpers.rule_engine import load_rules, evaluate

        # Load rules fresh from config each time
        rules = load_rules(self.agent)
        if not rules:
            return

        # Evaluate tool call against rules
        violation = evaluate(rules, tool_name, tool_args)
        if violation is None:
            return

        # Build block message
        rule_id = violation.get("id", "unknown")
        description = violation.get("description", "")
        block_message = violation.get(
            "block_message",
            f"RULE VIOLATION ({rule_id}): {description}"
        )
        suggested_tool = violation.get("suggested_tool", "")

        # Log the violation
        PrintStyle(font_color="yellow", padding=True).print(
            f"Rule Enforcer: Blocked '{tool_name}' - {rule_id}"
        )

        # Build full guidance message
        guidance = block_message
        if suggested_tool:
            guidance += f"\nSuggested alternative tool: {suggested_tool}"

        # Set kwargs['result'] as the blocking mechanism
        kwargs["result"] = guidance

        # Raise HandledException to reliably block tool execution
        raise HandledException(guidance)
