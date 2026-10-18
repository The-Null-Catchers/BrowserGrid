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
  const unnamedButtons = await page.locator('button:not([aria-label]):not([aria-labelledby])').evaluateAll(buttons => buttons.filter(button => !button.textContent?.trim() && !button.getAttribute('title')?.trim()).length);
  if (unnamedButtons > 0) findings.push({rule: 'button-name', count: unnamedButtons});
  const unnamedLinks = await page.locator('a[href]:not([aria-label]):not([aria-labelledby])').evaluateAll(links => links.filter(link => !link.textContent?.trim() && !link.querySelector('img[alt]:not([alt=""])') && !link.getAttribute('title')?.trim()).length);
  if (unnamedLinks > 0) findings.push({rule: 'link-name', count: unnamedLinks});
  return {checks: checks.length + 2, findings};
}
module.exports = {auditAccessibility};
