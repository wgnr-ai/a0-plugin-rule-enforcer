# Rule Enforcer Plugin

Enforces configurable behavioral rules at the tool execution layer. Blocks tool calls that violate rules and returns corrective guidance to the agent.

## How It Works

The plugin registers a `tool_execute_before` lifecycle extension that intercepts every tool call before execution. It evaluates the tool name and arguments against a list of configurable rules. If a rule is violated, the extension raises before the tool executes, so the call is blocked and the rule's guidance is returned to the agent as the tool error.

### Blocking mechanics (v1.1.0)

- Blocking uses `HandledException` raised from the hook — the supported mechanism on Agent Zero v2.13+.
- Argument mutation in `tool_execute_before` is NOT supported by the framework (args are not re-read after the hook; upstream issue #1926). This plugin never mutates tool args.
- Evaluation errors (e.g. a malformed rule) fail open: the call proceeds and the error is logged.

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
| `path_pattern` | string | Regex matched against **path-like argument values only** (`path`, `file`, `source`, `destination`, etc. — free-text args like `content` are never matched) |
| `exclude_path_pattern` | string | Regex that excludes matching paths from the rule |
| `args_check` | dict | Map of argument name → regex pattern for specific arg matching |

### Logic

- **Within a condition**: All patterns must match (AND)
- **Across conditions**: Any condition matching triggers the rule (OR)
- Rules are evaluated in priority order (critical first)
- First matching rule wins; evaluation stops
- A condition with none of the four fields matches nothing (guarded against misconfiguration)

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

## Design lineage

The block-and-guide pattern here — deny the call, tell the agent why, suggest the right tool — comes from [wOS](https://wos.wgnr.ai), wgnr.ai's open behavioral standard for agent systems: declarative principles for agents, code-level enforcement for the cases where prompt language fails. Rule Enforcer is the point tool; wOS is the system it came from. If your rules file keeps growing to cover more behaviors, that's the signal it's worth a look.

## Dependencies

- Python `re` module only (no external dependencies)
- Agent Zero helpers: `helpers.extension`, `helpers.print_style`, `helpers.errors`, `helpers.plugins`
