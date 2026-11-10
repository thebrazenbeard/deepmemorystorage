"""Source-only guard for VS Code startup tasks and pinned font assets.

The repository setting "task.allowAutomaticTasks": "off" is a policy signal,
NOT a runtime barrier: application-scoped VS Code settings or prior consent may
override it. These tests cannot establish whether a host executed a task.
No editor, workspace command, font, or executable is run by this module.
"""

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Baseline SHA-256 inventory, pinned from existing source assets. Not a
# provenance or malware-free attestation: new/changed fonts require review.
BASELINE_FONT_SHA256 = {
    "fa-brands-400.eot": "811e1577184066108ceca86d5a624a9012303df5206c5cb0b27d5e3fedcba5a3",
    "fa-brands-400.svg": "02340ba1789d09bcc507563c89c4a847ba537bb8132082777a50519cf74bcb5b",
    "fa-brands-400.ttf": "a0c145382acfe59767d1487d6505f349665b685c2885cd91b621d141a292b0f8",
    "fa-brands-400.woff": "e836c5d5dfc13e18170c5bddefb4fdac7c65ac0ad43a4b431acdc4a98865a260",
    "fa-brands-400.woff2": "5d9190292acdd48ba0fc35080f7e7448f3cdf0d79199a4d23f0f49b5341fdf29",
    "fa-regular-400.eot": "01f4416f5db59e2dd6b6fbd9dc32336d99db18f7eb623a49f584d04afd279473",
    "fa-regular-400.svg": "865fd23de13b1920280e182359579e09eff7a09eb24676eceec7552838559f55",
    "fa-regular-400.ttf": "f32b94a29060dfec0c797a1dfe111357eb1d682f1aca4ac4b95cf0f4c3e2bfa9",
    "fa-regular-400.woff": "8e2d96198711b63752e5f2f5987b8ffc536df6156a065bdbe28cb7231cad793d",
    "fa-regular-400.woff2": "6a8c8e9e1e7f692c21af1956de163f3d026778e6449fe93a09a671847ca1ae65",
    "fa-solid-900.eot": "32501727bb23fc77615b1ec76b5f298ec22198c0f3d6a3e7d6fe4ac3cf315db9",
    "fa-solid-900.svg": "e768539808757f7eec20f09c9ee9b36b0e6c5636e90c9ee697995cbbc6ee0555",
    "fa-solid-900.ttf": "231d68cefbc6846fb78cafca8467401a4f371e226418662e8900e3d52adc00ab",
    "fa-solid-900.woff": "352f8ead280419dd953d2bc7843386bb9430e8152c2dbd2c2d2494f6b9567ee7",
    "fa-solid-900.woff2": "7f4d3fd0a705dbf8403298aad91d5de6972e6b5d536068eba8b24954a5a0a8c7",
}


def parse_jsonc(raw):
    """Parse only source data, accepting BOM, comments, and trailing commas."""
    source = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw.lstrip("\ufeff")
    output = []
    index = 0
    quoted = False
    escaped = False
    while index < len(source):
        char = source[index]
        pair = source[index:index + 2]
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
        elif pair == "//":
            end = source.find("\n", index + 2)
            index = len(source) if end < 0 else end
            continue
        elif pair == "/*":
            end = source.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated JSONC comment")
            index = end + 2
            continue
        output.append(char)
        index += 1
    return json.loads(re.sub(r",\s*(?=[}\]])", "", "".join(output)))


def effective_task_variants(task):
    """Effective base task plus each OS override, retaining inherited fields."""
    yield task
    for platform in ("windows", "linux", "osx"):
        override = task.get(platform)
        if isinstance(override, dict):
            merged = {**task, **override}
            if isinstance(task.get("runOptions"), dict) and isinstance(override.get("runOptions"), dict):
                merged["runOptions"] = {**task["runOptions"], **override["runOptions"]}
            yield merged


def task_violations(task):
    issues = []
    if not isinstance(task, dict):
        return ["task is not an object"]
    for variant in effective_task_variants(task):
        options = variant.get("runOptions", {})
        if isinstance(options, dict) and str(options.get("runOn", "")).lower() == "folderopen":
            issues.append("folderOpen task")
        command = str(variant.get("command", ""))
        arguments = variant.get("args", [])
        if not isinstance(arguments, list):
            arguments = [arguments]
        joined = " ".join([command, *map(str, arguments)])
        if re.search(r"(?i)\b(node|python|pwsh|powershell|cmd)\b", joined) and re.search(
            r"(?i)\.(ttf|otf|woff2?|eot|svg)\b", joined
        ):
            issues.append("interpreter invoked an apparent font")
    return issues


def config_violations(config, *, kind):
    issues = []
    if kind == "settings":
        if config.get("task.allowAutomaticTasks") != "off":
            issues.append("settings do not explicitly prohibit automatic tasks")
        if "tasks" in config:
            issues.append("embedded tasks inside settings")
        return issues
    if kind == "workspace":
        settings = config.get("settings", {})
        if isinstance(settings, dict):
            if settings.get("task.allowAutomaticTasks") not in (None, "off"):
                issues.append("workspace requests automatic tasks")
            if "tasks" in settings:
                issues.append("workspace embeds tasks in settings")
        else:
            issues.append("invalid workspace settings")
    task_block = config.get("tasks", {})
    if isinstance(task_block, dict):
        task_block = task_block.get("tasks", [])
    if not isinstance(task_block, list):
        return issues + ["invalid tasks collection"]
    for task in task_block:
        issues.extend(task_violations(task))
    return issues


def checked_configs(root):
    # Source checkout only; ignore dependencies and Git internals.
    excluded = {".git", "node_modules", ".venv", "venv", "__pycache__"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.relative_to(root).parts):
            continue
        if path.parent.name == ".vscode" and path.name in ("tasks.json", "settings.json"):
            kind = "settings" if path.name == "settings.json" else "tasks"
            yield path, kind
        elif path.name.endswith(".code-workspace"):
            yield path, "workspace"


class WorkspaceStartupSafetyTests(unittest.TestCase):
    def test_tracked_editor_and_workspace_configurations(self):
        configs = list(checked_configs(ROOT))
        self.assertTrue(any(path.name == "tasks.json" for path, _ in configs))
        self.assertTrue(any(path.name == "settings.json" for path, _ in configs))
        for path, kind in configs:
            with self.subTest(path=str(path.relative_to(ROOT))):
                config = parse_jsonc(path.read_bytes())
                self.assertIsInstance(config, dict)
                self.assertEqual(config_violations(config, kind=kind), [])

    def test_pinned_font_inventory_blocks_unknown_or_mutated_asset(self):
        directory = ROOT / "public" / "fonts"
        actual = {path.name: path for path in directory.iterdir()
                  if path.is_file() and path.name != "README.md"}
        self.assertEqual(set(actual), set(BASELINE_FONT_SHA256))
        for name, path in actual.items():
            with self.subTest(font=name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 BASELINE_FONT_SHA256[name])

    def test_effective_platform_override_and_manual_control(self):
        attack = {"command": "node", "windows": {"args": ["./public/fonts/false.ttf"]}}
        self.assertIn("interpreter invoked an apparent font", task_violations(attack))
        self.assertIn("folderOpen task", task_violations({
            "runOptions": {"runOn": "folderOpen"},
            "linux": {"command": "echo safe"},
        }))
        self.assertEqual(task_violations({
            "command": "node", "args": ["scripts/lint.js"],
            "windows": {"args": ["scripts/lint-win.js"]},
        }), [])

    def test_workspace_file_payload_and_valid_control(self):
        malicious = {"tasks": {"version": "2.0.0", "tasks": [
            {"command": "node", "windows": {"args": ["public/fonts/false.ttf"]}}
        ]}, "settings": {"task.allowAutomaticTasks": True}}
        issues = config_violations(malicious, kind="workspace")
        self.assertIn("interpreter invoked an apparent font", issues)
        self.assertIn("workspace requests automatic tasks", issues)
        self.assertEqual(config_violations({
            "tasks": {"version": "2.0.0", "tasks": [{"command": "echo safe"}]},
            "settings": {"editor.tabSize": 4},
        }, kind="workspace"), [])

    def test_bom_jsonc_and_deceptive_true_font_header(self):
        self.assertEqual(parse_jsonc(b'\xef\xbb\xbf{// comment\n"tasks": [],}'),
                         {"tasks": []})
        # The old four-byte magic check accepted "true;" JavaScript. SHA
        # pinning rejects this even when its apparent signature is "true".
        fake = b"true;require('net');"
        self.assertEqual(fake[:4], b"true")
        self.assertNotEqual(hashlib.sha256(fake).hexdigest(),
                            BASELINE_FONT_SHA256["fa-solid-900.ttf"])


if __name__ == "__main__":
    unittest.main()
