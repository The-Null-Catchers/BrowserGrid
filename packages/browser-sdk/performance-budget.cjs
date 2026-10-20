'use strict';
// Evaluate explicitly configured performance thresholds without inventing measurements.
const METRICS = ['navigation_duration_ms','dom_content_loaded_ms','load_event_ms','first_paint_ms','first_contentful_paint_ms'];
function evaluatePerformanceBudget(timing, budgets) {
  if (!budgets || typeof budgets !== 'object' || Array.isArray(budgets)) throw new TypeError('Performance budgets must be an object');
  const keys = Object.keys(budgets);
  if (!keys.length) throw new TypeError('At least one performance budget is required');
  for (const key of keys) if (!METRICS.includes(key)) throw new TypeError('Unknown performance budget metric: ' + key);
  const results = [];
  for (const metric of METRICS) {
    if (!Object.prototype.hasOwnProperty.call(budgets, metric)) continue;
    const limit = budgets[metric];
    if (!Number.isFinite(limit) || limit < 0) throw new TypeError('Invalid performance budget for ' + metric);
    const measured = timing?.[metric];
    const available = Number.isFinite(measured) && measured >= 0;
    results.push({metric, limit_ms:limit, observed_ms:available?measured:null, status:available?(measured<=limit?'pass':'fail'):'unavailable'});
  }
  return {passed:results.every(row=>row.status==='pass'), results};
}
module.exports = {evaluatePerformanceBudget, METRICS};
