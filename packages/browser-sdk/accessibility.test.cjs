const {test}=require('node:test');
const {strict:assert}=require('node:assert');
const {auditAccessibility}=require('./accessibility.cjs');

test('basic accessibility scan checks three categories and reports real counts', async()=>{
  const requested=[];
  const page={locator(selector){requested.push(selector);return {count:async()=>selector==='img:not([alt])'?2:selector.startsWith('html')?1:0};}};
  const result=await auditAccessibility(page);
  assert.equal(result.checks,3);
  assert.deepEqual(result.findings,[{rule:'html-lang',count:1},{rule:'image-alt',count:2}]);
  assert.equal(requested.length,3);
});

test('basic accessibility scan omits categories without findings', async()=>{
  const page={locator(){return {count:async()=>0};}};
  assert.deepEqual(await auditAccessibility(page),{checks:3,findings:[]});
});
