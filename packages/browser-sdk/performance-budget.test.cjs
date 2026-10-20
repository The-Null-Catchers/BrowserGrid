const {test}=require('node:test');
const assert=require('node:assert/strict');
const {evaluatePerformanceBudget}=require('./performance-budget.cjs');
test('passes timings within configured budgets',()=>{
 assert.deepEqual(evaluatePerformanceBudget({navigation_duration_ms:400},{navigation_duration_ms:500}),{
 passed:true,results:[{metric:'navigation_duration_ms',limit_ms:500,observed_ms:400,status:'pass'}]});
});
test('fails when a measured timing exceeds its budget',()=>{
 const result=evaluatePerformanceBudget({first_contentful_paint_ms:1200},{first_contentful_paint_ms:1000});
 assert.equal(result.passed,false);
 assert.equal(result.results[0].status,'fail');
});
test('missing metrics are not silently considered passing',()=>{
 const result=evaluatePerformanceBudget({}, {first_paint_ms:500});
 assert.equal(result.passed,false);
 assert.equal(result.results[0].status,'unavailable');
});
test('rejects invalid performance thresholds',()=>{
 assert.throws(()=>evaluatePerformanceBudget({}, {navigation_duration_ms:-1}),TypeError);
});
