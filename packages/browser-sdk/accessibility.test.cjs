const {test}=require('node:test');
const {strict:assert}=require('node:assert');
const {auditAccessibility}=require('./accessibility.cjs');

test('basic accessibility scan checks three categories and reports real counts', async()=>{
  const requested=[];
  const page={locator(selector){requested.push(selector);return {count:async()=>selector==='img:not([alt])'?2:selector.startsWith('html')?1:0,evaluateAll:async()=>0};}};
  const result=await auditAccessibility(page);
  assert.equal(result.checks,5);
  assert.deepEqual(result.findings,[{rule:'html-lang',count:1},{rule:'image-alt',count:2}]);
  assert.equal(requested.length,5);
});

test('basic accessibility scan omits categories without findings', async()=>{
  const page={locator(){return {count:async()=>0,evaluateAll:async()=>0};}};
  assert.deepEqual(await auditAccessibility(page),{checks:5,findings:[]});
});

test('button without a usable name is reported', async()=>{
  const page={locator(){return {count:async()=>0,evaluateAll:async()=>2};}};
  assert.deepEqual(await auditAccessibility(page),{checks:5,findings:[{rule:'button-name',count:2},{rule:'link-name',count:2}]});
});

test('unnamed link findings are counted', async()=>{
 const page={locator(selector){return {count:async()=>0,evaluateAll:async()=>selector.startsWith('a[href]')?3:0};}};
 assert.deepEqual(await auditAccessibility(page),{checks:5,findings:[{rule:'link-name',count:3}]});
});
