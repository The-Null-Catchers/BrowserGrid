const {test}=require('node:test');
const {strict:assert}=require('node:assert');
const {auditAccessibility}=require('./accessibility.cjs');

test('basic accessibility scan checks three categories and reports real counts', async()=>{
  const requested=[];
  const page={locator(selector){requested.push(selector);return {count:async()=>selector==='img:not([alt])'?2:selector.startsWith('html')?1:0,evaluateAll:async()=>0};}};
  const result=await auditAccessibility(page);
  assert.equal(result.checks,7);
  assert.deepEqual(result.findings,[{rule:'html-lang',count:1},{rule:'image-alt',count:2}]);
  assert.equal(requested.length,7;
});

test('basic accessibility scan omits categories without findings', async()=>{
  const page={locator(){return {count:async()=>0,evaluateAll:async()=>0};}};
  assert.deepEqual(await auditAccessibility(page),{checks:7,findings:[]});
});

test('button without a usable name is reported', async()=>{
  const page={locator(selector){return {count:async()=>0,evaluateAll:async()=>selector==='head title'?false:2};}};
  assert.deepEqual(await auditAccessibility(page),{checks:7,findings:[{rule:'button-name',count:2},{rule:'link-name',count:2}]});
});

test('unnamed link findings are counted', async()=>{
 const page={locator(selector){return {count:async()=>0,evaluateAll:async()=>selector.startsWith('a[href]')?3:0};}};
 assert.deepEqual(await auditAccessibility(page),{checks:7,findings:[{rule:'link-name',count:3}]});
});

test('missing document title is a finding',async()=>{
 const page={locator(selector){return {count:async()=>0,evaluateAll:async()=>selector==='head title'};}};
 assert.deepEqual(await auditAccessibility(page),{checks:7,findings:[{rule:'document-title',count:1}]});
});

test('image submission inputs without alt or ARIA names are reported',async()=>{
 const page={locator(selector){return {count:async()=>selector.startsWith('input[type="image"]')?2:0,evaluateAll:async()=>false};}};
 assert.deepEqual(await auditAccessibility(page),{checks:7,findings:[{rule:'input-image-alt',count:2}]});
});
