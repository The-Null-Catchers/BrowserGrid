"""Run real Playwright tests without page fixtures and parse their actual JSON report.

This validates CLI/config/reporter/parser interoperability, not browser or Docker execution.
Requires npm ci in runtimes and the installed BrowserGrid Python dependencies.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile

from browsergrid.results import parse_report


def main():
    root = Path(__file__).resolve().parents[2]
    modules = root / "runtimes/node_modules"
    cli = modules / "playwright/cli.js"
    if not cli.is_file():
        raise RuntimeError("Install pinned runtime dependencies with: cd runtimes && npm ci")
    with tempfile.TemporaryDirectory(prefix="browsergrid-report-") as directory:
        project = Path(directory)
        (project / "node_modules").symlink_to(modules, target_is_directory=True)
        tests = project / "tests"
        tests.mkdir()
        (tests / "outcomes.spec.cjs").write_text(
            """const {test,expect}=require('@playwright/test');
test('passed',async({},info)=>{
  expect(info.project.name).toBe('chromium');
  expect(info.project.use.viewport.width).toBe(1440);
});
test('failed',async()=>{expect('actual').toBe('different');});
test('flaky',async({},info)=>{expect(info.retry).toBe(1);});
test.skip('skipped',async()=>{throw new Error('must not run');});
test('expected failure',async()=>{test.fail();expect(1).toBe(2);});
test('timed out',async()=>{test.setTimeout(50);await new Promise(resolve=>setTimeout(resolve,500));});
"""
        )
        original = project / "playwright.config.cjs"
        original.write_text(
            "module.exports={testDir:'./missing',retries:0,"
            "projects:[{name:'wrong',use:{browserName:'firefox'}}],"
            "use:{viewport:{width:800,height:600}}};\n"
        )
        report = project / "report.json"
        enforced = {
            "testDir": str(tests),
            "outputDir": str(project / "output"),
            "workers": 1,
            "retries": 1,
            "timeout": 5000,
            "reporter": [
                [str(root / "runtimes/reporter.cjs")],
                ["json", {"outputFile": str(report)}],
            ],
            "projects": [{"name": "chromium", "use": {"browserName": "chromium"}}],
            "use": {"viewport": {"width": 1440, "height": 900}},
        }
        generator = subprocess.run(
            [
                "node",
                "-e",
                "process.stdout.write(require(process.argv[1]).generatedConfigSource("
                "process.argv[2],JSON.parse(process.argv[3])))",
                str(root / "runtimes/config.cjs"),
                str(original),
                json.dumps(enforced),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        config = project / "browsergrid.config.ts"
        config.write_text(generator.stdout)

        def run(*arguments):
            return subprocess.run(
                ["node", str(cli), "test", "--config", str(config), *arguments],
                cwd=project,
                env={**os.environ, "CI": "1", "FORCE_COLOR": "0"},
                capture_output=True,
                text=True,
                timeout=60,
            )

        completed = run()
        assert completed.returncode == 1, completed.stdout + completed.stderr
        rows, errors = parse_report(report.read_bytes())
        assert not errors, errors
        by_title = {row["title"]: row for row in rows}
        assert len(rows) == 6
        assert {title: row["status"] for title, row in by_title.items()} == {
            "passed": "passed",
            "failed": "failed",
            "flaky": "flaky",
            "skipped": "skipped",
            "expected failure": "passed",
            "timed out": "timed_out",
        }, rows
        assert by_title["failed"]["retry"] == by_title["flaky"]["retry"] == 1
        assert by_title["expected failure"]["retry"] == 0
        assert by_title["failed"]["error"] and by_title["flaky"]["error"]
        events = [
            json.loads(line[4:])
            for line in completed.stdout.splitlines()
            if line.startswith("@bg:")
        ]
        starts = [event for event in events if event["kind"] == "test_start"]
        ends = [event for event in events if event["kind"] == "test_end"]
        assert len(starts) == len(ends) == 9, events
        assert any(event["status"] == "skipped" for event in ends)
        assert any(event["retry"] == 1 and event["status"] == "passed" for event in ends)
        assert all(event["duration_ms"] >= 0 for event in ends)
        passed = run("--grep", "passed$")
        assert passed.returncode == 0, passed.stdout + passed.stderr
        rows, errors = parse_report(report.read_bytes())
        assert not errors and len(rows) == 1 and rows[0]["status"] == "passed", rows

        # A load/configuration failure is distinct from a user's failed assertion.
        (tests / "outcomes.spec.cjs").write_text("throw new Error('contract discovery error');\n")
        discovery = run()
        assert discovery.returncode == 1, discovery.stdout + discovery.stderr
        rows, errors = parse_report(report.read_bytes())
        assert not rows and errors
        assert any("contract discovery error" in error.get("message", "") for error in errors)
    print("Real Playwright CLI/config/reporter -> BrowserGrid parser contract passed (no browser).")


if __name__ == "__main__":
    main()
