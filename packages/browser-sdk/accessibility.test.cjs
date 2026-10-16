const {test}=require('node:test');
const {strict:assert}=require('node:assert');
const {auditAccessibility}=require('./accessibility.cjs');
test('exports the preflight check',()=>assert.equal(typeof auditAccessibility,'function'));
