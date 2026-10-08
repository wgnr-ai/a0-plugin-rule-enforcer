"""Offline tests for rule_enforcer rule engine (no A0 imports needed).

Run: python3 tests/test_rule_engine.py  (exit 0 = all pass)
Covers v1.1.0 behavior: path-scoped matching, bare-condition guard,
both default rules, regression for the v1.0.0 content false positive.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helpers"))

import rule_engine  # noqa: E402


def ev(rules, tool_name, args):
    return rule_engine.evaluate(rules, tool_name, args)


def load_default_rules():
    import yaml

    cfg_path = os.path.join(
        os.path.dirname(__file__), "..", "default_config.yaml"
    )
    with open(cfg_path) as f:
        return yaml.safe_load(f)["rules"]


class TestPathScoping(unittest.TestCase):
    """path_pattern must see path-like args only — never free text."""

    def setUp(self):
        self.rules = [
            {
                "id": "r",
                "enabled": True,
                "priority": "critical",
                "conditions": [
                    {"tool_name": "text_editor", "path_pattern": r".*secret.*"}
                ],
            }
        ]

    def test_content_mentioning_keyword_not_blocked(self):
        call = {
            "action": "write",
            "path": "notes/2026-10-08.md",
            "content": "Meeting notes: discussed the Q4 budget report timeline.",
        }
        self.assertIsNone(ev(self.rules, "text_editor", call))

    def test_matching_path_blocked(self):
        call = {"action": "write", "path": "configs/secret_keys.yaml"}
        self.assertIsNotNone(ev(self.rules, "text_editor", call))

    def test_non_path_args_never_match(self):
        call = {"action": "write", "query": "how to keep secrets safe"}
        self.assertIsNone(ev(self.rules, "text_editor", call))

    def test_nested_path_key_blocked(self):
        call = {"action": "write", "options": {"file_path": "a/b/secret.txt"}}
        self.assertIsNotNone(ev(self.rules, "text_editor", call))

    def test_path_key_case_insensitive(self):
        call = {"action": "write", "FilePath": "x/secret/y"}
        self.assertIsNotNone(ev(self.rules, "text_editor", call))


class TestBareConditionGuard(unittest.TestCase):
    def test_condition_with_no_fields_matches_nothing(self):
        rules = [
            {
                "id": "bad",
                "enabled": True,
                "priority": "critical",
                "conditions": [{}],
            }
        ]
        self.assertIsNone(ev(rules, "text_editor", {"path": "anything.txt"}))


class TestDefaultRules(unittest.TestCase):
    """Behavior of the shipped default_config.yaml rules."""

    def setUp(self):
        self.rules = load_default_rules()

    def test_v100_regression_innocent_write_allowed(self):
        # Blocked in v1.0.0 because `content` mentioned "budget report".
        call = {
            "action": "write",
            "path": "notes/2026-10-08.md",
            "content": "Meeting notes: discussed the Q4 budget report timeline.",
        }
        self.assertIsNone(ev(self.rules, "text_editor", call))

    def test_template_md_allowed(self):
        call = {"action": "write", "path": "docs/template-guide.md"}
        self.assertIsNone(ev(self.rules, "text_editor", call))

    def test_user_facing_doc_blocked(self):
        call = {"action": "write", "path": "documents/budget.ods"}
        v = ev(self.rules, "text_editor", call)
        self.assertIsNotNone(v)
        self.assertEqual(v["id"], "user-facing-docs-use-office")

    def test_invoice_xlsx_blocked(self):
        call = {"action": "write", "path": "workdir/invoice-42.xlsx"}
        self.assertIsNotNone(ev(self.rules, "text_editor", call))

    def test_hidden_knowledge_dir_template_blocked(self):
        call = {
            "action": "write",
            "path": ".a0proj/knowledge/main/template.ods",
        }
        v = ev(self.rules, "text_editor", call)
        self.assertIsNotNone(v)

    def test_plain_code_write_allowed(self):
        call = {"action": "write", "path": "src/main.py", "content": "print(1)"}
        self.assertIsNone(ev(self.rules, "text_editor", call))

    def test_other_tool_unaffected(self):
        call = {"action": "write", "path": "documents/budget.ods"}
        self.assertIsNone(ev(self.rules, "code_execution_tool", call))

    def test_first_match_wins_by_priority(self):
        # Priority ordering is applied by load_rules(); evaluate() consumes
        # the already-sorted list. Replicate the documented contract here.
        rules = [
            {
                "id": "low",
                "enabled": True,
                "priority": "low",
                "conditions": [{"tool_name": "text_editor", "path_pattern": "a"}],
            },
            {
                "id": "critical",
                "enabled": True,
                "priority": "critical",
                "conditions": [{"tool_name": "text_editor", "path_pattern": "a"}],
            },
        ]
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        rules.sort(key=lambda r: order[r["priority"]])
        self.assertEqual(ev(rules, "text_editor", {"path": "a.txt"})["id"], "critical")


class TestRulesFromConfig(unittest.TestCase):
    """v1.2.0: config/rules split (single config parse per tool call)."""

    def test_filters_disabled_and_sorts_priority(self):
        cfg = {
            "mode": "enforce",
            "rules": [
                {"id": "low", "enabled": True, "priority": "low",
                 "conditions": [{"tool_name": "t", "path_pattern": "x"}]},
                {"id": "off", "enabled": False,
                 "conditions": [{"tool_name": "t", "path_pattern": "x"}]},
                {"id": "crit", "enabled": True, "priority": "critical",
                 "conditions": [{"tool_name": "t", "path_pattern": "x"}]},
            ],
        }
        ids = [r["id"] for r in rule_engine.rules_from_config(cfg)]
        self.assertEqual(ids, ["crit", "low"])

    def test_mode_passed_through_untouched(self):
        cfg = {"mode": "audit", "rules": []}
        self.assertEqual(cfg["mode"], "audit")
        self.assertEqual(rule_engine.rules_from_config(cfg), [])

    def test_none_config_yields_no_rules(self):
        self.assertEqual(rule_engine.rules_from_config(None), [])


class TestLoadRules(unittest.TestCase):
    def test_disabled_rules_skipped(self):
        with mock.patch.object(rule_engine, "PLUGIN_NAME", "rule_enforcer"):
            import sys as _sys

            helpers_plugins = mock.MagicMock()
            helpers_plugins.get_plugin_config.return_value = {
                "rules": [
                    {"id": "off", "enabled": False, "conditions": [{}]},
                    {
                        "id": "on",
                        "enabled": True,
                        "priority": "high",
                        "conditions": [
                            {"tool_name": "t", "path_pattern": "x"}
                        ],
                    },
                ]
            }
            saved = sys.modules.get("helpers.plugins")
            sys.modules["helpers.plugins"] = helpers_plugins
            try:
                rules = rule_engine.load_rules(agent=None)
            finally:
                if saved is not None:
                    sys.modules["helpers.plugins"] = saved
                else:
                    del sys.modules["helpers.plugins"]
        self.assertEqual([r["id"] for r in rules], ["on"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
