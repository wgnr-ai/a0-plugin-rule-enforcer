# Rule Enforcer Plugin

Enforces configurable behavioral rules at the tool execution layer. Blocks tool calls that violate rules and returns corrective guidance to the agent.

## How It Works

The plugin registers a `tool_execute_before` lifecycle extension that intercepts every tool call before execution. It evaluates the tool name and arguments against a list of configurable rules. If a rule is violated, the tool call is blocked and a descriptive error message is returned to the agent.

## Rules

Rules are defined in `default_config.yaml` (or overridden via plugin config). Each rule has:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique rule identifier |
| `description` | string | Human-readable rule description |
| `priority` | string | `critical`, `high`, `medium`, or `low` (controls evaluation order) |
| `enabled` | bool | Whether the rule is active |
| `conditions` | list | List of conditions (OR logic — any match triggers the rule) |
| `block_message` | string | Message returned to the agent when the rule fires |
| `suggested_tool` | string | Optional alternative tool to suggest |

### Conditions

Each condition is a set of patterns that must ALL match (AND logic):

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Must match exactly |
| `path_pattern` | string | Regex matched against any path-like argument value |
| `exclude_path_pattern` | string | Regex that excludes matching paths from the rule |
| `args_check` | dict | Map of argument name → regex pattern for specific arg matching |

### Logic

- **Within a condition**: All patterns must match (AND)
- **Across conditions**: Any condition matching triggers the rule (OR)
- Rules are evaluated in priority order (critical first)
- First matching rule wins; evaluation stops

## Default Rules

### `user-facing-docs-use-office`

Blocks `text_editor` when the path contains user-facing document keywords (template, form, tracker, budget, invoice, etc.) unless the path is in a framework/config directory.

**Suggests:** `office_artifact`

### `no-hidden-dir-templates`

Blocks `text_editor` when templates/forms are saved to hidden framework directories (`.a0proj/knowledge/`, `.a0proj/memory/`, `.git/`).

**Suggests:** `office_artifact`

## Adding Custom Rules

Edit `default_config.yaml` or override via plugin config:

```yaml
rules:
  - id: my-custom-rule
    description: Description of what this rule enforces
    priority: medium
    enabled: true
    conditions:
      - tool_name: "text_editor"
        path_pattern: ".*secret.*"
    block_message: "RULE VIOLATION: Cannot edit files in secret directories."
    suggested_tool: ""
```

## File Structure

```
rule_enforcer/
├── plugin.yaml                          # Plugin manifest
├── default_config.yaml                  # Default rules
├── README.md                            # This file
├── extensions/
│   └── python/
│       └── tool_execute_before/
│           └── _10_rule_validator.py     # Enforcement extension
└── helpers/
    └── rule_engine.py                   # Pure pattern matching engine
```

## Dependencies

- Python `re` module only (no external dependencies)
- Agent Zero helpers: `helpers.extension`, `helpers.print_style`, `helpers.errors`, `helpers.plugins`
