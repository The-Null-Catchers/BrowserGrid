# Browser performance budgets

The browser SDK records real navigation and paint timings in `performance.json`.
You can optionally evaluate five timing metrics against maximum allowed milliseconds.

Configure the browser runtime (not the control-plane API) with:

```sh
BG_PERFORMANCE_BUDGETS='{"navigation_duration_ms":3000,"first_contentful_paint_ms":1800}'
```

Supported metrics: `navigation_duration_ms`, `dom_content_loaded_ms`,
`load_event_ms`, `first_paint_ms`, `first_contentful_paint_ms`.
All thresholds are finite non-negative numbers in milliseconds.

When configured, each test receives a `performance-budget.json` artifact with
`pass`, `fail`, or `unavailable` for each metric. A missing paint entry
is **not** interpreted as a passing result. Invalid, empty, or unknown metric
settings produce an error report rather than a false pass.

By default, findings are informational. To fail tests when any configured
budget is exceeded, unavailable, or invalid, also set:

```sh
BG_PERFORMANCE_BUDGET_ENFORCE=1
```

The failure is reported only after the JSON and other diagnostic artifacts
have been attached. Browser performance measurements vary by hardware,
load, cache, and runner conditions. Calibrate thresholds on representative
runners before enabling enforcement. This feature does not yet configure
budgets through the web dashboard or attach them to a project database
record; runtime environment variables are currently required.
