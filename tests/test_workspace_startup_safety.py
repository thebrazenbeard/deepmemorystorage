"""Source-only regression checks for editor-open execution and disguised assets.

Do not invoke VS Code, task commands, or assets in this test.
"""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FONT_MAGIC = {
    ".ttf": (b"\x00\x01\x00\x00", b"true", b"ttcf"),
    ".otf": (b"OTTO",),
    ".woff": (b"wOFF",),
    ".woff2": (b"wOF2",),
}


def read_workspace_json(path):
    # utf-8-sig catches the malicious BOM case instead of throwing before inspection.
    source = path.read_text(encoding="utf-8-sig")
    return json.loads(re.sub(r",\s*(?=[}\]])", "", source))


def task_variants(task):
    yield task
    for platform in ("windows", "linux", "osx"):
        override = task.get(platform)
        if isinstance(override, dict):
            yield override


class WorkspaceStartupSafetyTests(unittest.TestCase):
    def test_no_folder_open_tasks_or_interpreter_font_commands(self):
        config = read_workspace_json(ROOT / ".vscode" / "tasks.json")
        tasks = config.get("tasks", [])
        self.assertIsInstance(tasks, list)
        for task in tasks:
            self.assertIsInstance(task, dict)
            for variant in task_variants(task):
                options = variant.get("runOptions", {})
                self.assertNotEqual(options.get("runOn"), "folderOpen")
                command = str(variant.get("command", ""))
                args = variant.get("args", [])
                combined = " ".join([command, *map(str, args if isinstance(args, list) else [args])])
                if re.search(r"(?i)\b(node|python|pwsh|powershell|cmd)\b", combined):
                    self.assertNotRegex(combined, r"(?i)\.(ttf|otf|woff2?)\b")

    def test_settings_explicitly_disable_automatic_tasks(self):
        settings = read_workspace_json(ROOT / ".vscode" / "settings.json")
        self.assertEqual(settings.get("task.allowAutomaticTasks"), "off")
        self.assertNotIn("tasks", settings)

    def test_public_fonts_have_font_signatures_not_javascript(self):
        font_dir = ROOT / "public" / "fonts"
        self.assertFalse((font_dir / "fa-solid-600.ttf").exists(), "counterfeit font loader")
        for candidate in font_dir.rglob("*"):
            if candidate.suffix.lower() not in FONT_MAGIC or not candidate.is_file():
                continue
            header = candidate.read_bytes()[:4]
            self.assertIn(header, FONT_MAGIC[candidate.suffix.lower()], str(candidate))

    def test_platform_override_and_bom_regressions(self):
        fake = {"command": "echo harmless", "windows": {"runOptions": {"runOn": "folderOpen"}}}
        self.assertTrue(any(v.get("runOptions", {}).get("runOn") == "folderOpen"
                            for v in task_variants(fake)))
        self.assertEqual(json.loads(b'\xef\xbb\xbf{"tasks": []}'.decode("utf-8-sig")), {"tasks": []})


if __name__ == "__main__":
    unittest.main()
