# BrowserGrid portfolio roadmap

Baseline reviewed on November 17, 2026. Repository roadmap published on November 18, 2026.

This roadmap applies to this repository and follows the shared Null Catchers portfolio plan. Verify the documented state against the current code and runs before starting work.

**Estimated initial demo effort** 30–50 hours for a developer familiar with the project. The estimate excludes external reviews, store accounts, target environment setup, and later milestones.

## Project priorities

**Documented state** The three browser engines run in isolation. CI has produced screenshots, traces, and recordings. Rich viewers, visual baselines, and GitHub checks remain roadmap items.

**P0 — Demo** Turn a deterministic failure into a walkthrough from the run result to its cause and evidence. Extend browser coverage where the walkthrough needs it.

**P1 — Validation and depth** Define a budget for existing performance data and add an axe-core check to a known page. Report the rules checked and the observed violations.

**P2 — Later** Add a visual baseline with image diffs and an approval step. Add GitHub checks afterward.

**Acceptance criteria** Successful and failing fixtures produce understandable statuses. Artifacts remain scoped to their workspace and come from real runs.

**Demo scenario** Reproduce a responsive defect at one viewport, inspect the evidence, fix the fixture, and rerun it. [ROADMAP](https://github.com/The-Null-Catchers/BrowserGrid/blob/main/docs/ROADMAP.md), [Validation](https://github.com/The-Null-Catchers/BrowserGrid/blob/main/docs/VALIDATION.md).

## Next milestones

The [validation record](docs/VALIDATION.md) documents runs on Chromium, Firefox, and WebKit.

1. [ ] Run a project-owned fixture that fails at a chosen browser and viewport size. Check that its name and failure match in the logs and UI.
2. [ ] Show the screenshot, trace, console output, and network log from that run. Verify that another workspace cannot access them.
3. [ ] Record the commit SHA, browser version, run ID, and trace viewing instructions.

## Portfolio acceptance checklist

- [ ] Another person can reproduce the primary workflow from a clean checkout using the README and test credentials or fixtures.
- [ ] The demo tells one complete story with a defined user, problem, and saved result.
- [ ] Tests cover the main flow, an important failure, and access boundaries when multiple accounts are involved.
- [ ] Demo data is labeled synthetic and reproducible. Review screenshots and recordings for secrets and customer data.
- [ ] Include four to six real screenshots where appropriate, a 60–120 second recording, and working links. Identify the revision used for capture.
- [ ] The README describes implemented capabilities, setup, architecture, limits, tests, and the demo.
- [ ] A short case study explains two engineering decisions, a considered alternative, and how the system handles an actual failure.
- [ ] Release evidence records the commit SHA, CI, prerequisites, and limits. Performance data includes workload, hardware, and method.
- [ ] Licensing and contributor attribution are settled before distribution. Choose the license for each repository individually.

A hosted demo is optional. Code execution, server administration, and secret management can be demonstrated through a recording and a reproducible isolated environment. Keep public demo access scoped to the activities it needs.

## Implementation and follow-up

- Break P0 into tasks with expected behavior, acceptance criteria, and a suitable test.
- Verify existing functionality first. Update this plan when evidence tied to a commit or PR closes a milestone.
- Record the fixture source, the revision used for evidence, and the tested limits.
- Review the final diff and verify required checks for its exact SHA before merging. Follow branch protection.
- For documentation-only changes with no applicable workflow, verify content and links and record the checks actually performed.
- Tie performance, security, and readiness claims to supporting evidence.

## Additional references

- [ROADMAP.md](docs/ROADMAP.md)
