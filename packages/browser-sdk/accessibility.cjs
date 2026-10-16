'use strict';
// Deterministic accessibility preflight; this is not an axe-core or WCAG audit.
async function auditAccessibility(page) {
  const checks = [
    ['html-lang', 'html:not([lang]), html[lang=""]'],
    ['image-alt', 'img:not([alt])'],
    ['form-label', 'input:not([type="hidden"]):not([aria-label]):not([aria-labelledby]):not([id]), textarea:not([aria-label]):not([aria-labelledby]):not([id])']
  ];
  const findings = [];
  for (const [rule, selector] of checks) {
    const count = await page.locator(selector).count();
    if (count > 0) findings.push({rule, count});
  }
  return {checks: checks.length, findings};
}
module.exports = {auditAccessibility};
