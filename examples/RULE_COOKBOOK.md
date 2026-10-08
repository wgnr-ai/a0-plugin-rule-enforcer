# Rule Cookbook

Copy-paste rule packs for `default_config.yaml` (or your plugin `config.json` override). All rules assume `tool_name`-based conditions; adjust tools/paths to your environment.

Start every new rule set in `"mode": "audit"` — watch the log for a few days, then flip to `enforce` once you've confirmed no false positives.

## Protect secrets and infra

Block edits to environment files, infrastructure definitions, and git internals:

```yaml
rules:
  - id: protect-secrets-and-infra
    description: Never modify .env files, infra/, or .git/ via text_editor
    priority: critical
    enabled: true
    conditions:
      - tool_name: "text_editor"
        path_pattern: "(\\.env$|\\.env\\.|(^|/)\\.git/|(^|/)infra/)"
    block_message: "RULE VIOLATION: This path is protected (secrets/infra). Changes here require human review - surface the change to the user instead of editing."
    suggested_tool: ""
```

## Office documents go to the office tool

Route user-facing documents (invoices, budgets, forms) to a document tool instead of raw text editing:

```yaml
rules:
  - id: user-docs-use-office
    description: User-facing documents must be produced with the office tool
    priority: critical
    enabled: true
    conditions:
      - tool_name: "text_editor"
        path_pattern: ".*(documents/|workdir/).*\\.(ods|odt|odp|xlsx|docx|pptx)$"
    block_message: "RULE VIOLATION: Use the office_artifact tool (desktop suite) for user-facing documents, not text_editor."
    suggested_tool: "office_artifact"
```

## Keep templates out of framework directories

Agents sometimes "tidy" templates into knowledge/memory/git directories where users can't reach them:

```yaml
rules:
  - id: no-hidden-dir-templates
    description: Templates and forms must not be saved to hidden framework directories
    priority: high
    enabled: true
    conditions:
      - tool_name: "text_editor"
        path_pattern: ".*(template|form|tracker).*"
        args_check:
          path: "((^|/)\\.a0proj/(knowledge|memory)/|(^|/)\\.git/)"
    block_message: "RULE VIOLATION: Save templates to an accessible directory (documents/), not hidden framework directories."
    suggested_tool: ""
```

## No agent edits to agent definitions

Prevent an agent from rewriting its own (or siblings') role definitions:

```yaml
rules:
  - id: no-self-agent-edits
    description: Agents must not edit .a0proj/agents/ definitions
    priority: critical
    enabled: true
    conditions:
      - tool_name: "text_editor"
        args_check:
          path: "\\.a0proj/agents/.*/agent\\.yaml$"
    block_message: "RULE VIOLATION: Agent definitions are human-managed. Propose the change to the user instead of editing agent.yaml."
    suggested_tool: ""
```

## Per-project / per-agent overrides

Set `per_project_config: true` / `per_agent_config: true` in `plugin.yaml` (v1.2.0+) and drop a `config.json` in:

- `<project>/.a0proj/plugins/rule_enforcer/config.json` — project-scoped rules
- `usr/agents/<profile>/plugins/rule_enforcer/config.json` — agent-scoped rules

More-specific configs override the global one; keep only the rules that differ in the scoped file.
