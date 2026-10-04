const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {executionCommand, generatedConfigSource, processExitCode} = require('../config.cjs');

test('repository default uses project Playwright CLI',()=>{
  const command=['/opt/browsergrid/node_modules/.bin/playwright','test'];
  assert.equal(executionCommand(command,'/work/source',false)[0],'/work/source/node_modules/.bin/playwright');
  assert.equal(executionCommand(command,'/work/source',true)[0],command[0]);
  assert.deepEqual(command,['/opt/browsergrid/node_modules/.bin/playwright','test']);
});
test('generated config contains actual newlines',()=>{
  const source=generatedConfigSource(null,{workers:1});
  assert.ok(source.includes('\nexport default'));
  assert.ok(!source.includes('\\n'));
});
test('instrumented repository fixture loads without a second Playwright instance',()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'browsergrid-module-'));
  try{
    const localModules=path.join(root,'node_modules');
    // A separate physical installation catches accidental imports from the runtime copy.
    fs.cpSync(path.resolve(__dirname,'../node_modules'),localModules,{recursive:true});
    fs.mkdirSync(path.join(localModules,'@browsergrid'),{recursive:true});
    fs.symlinkSync(path.resolve(__dirname,'../../packages/browser-sdk'),path.join(localModules,'@browsergrid/test'),'dir');
    fs.mkdirSync(path.join(root,'tests'));
    fs.writeFileSync(path.join(root,'tests/module.spec.js'),"const {test,expect}=require('@browsergrid/test');test('repository discovery',async()=>{expect(1).toBe(1)});");
    fs.writeFileSync(path.join(root,'playwright.config.js'),"module.exports={testDir:'./tests',reporter:'list'};");
    const child=spawnSync(process.execPath,[path.join(localModules,'playwright/cli.js'),'test','--list'],{
      cwd:root,env:{...process.env,BG_PROJECT_ROOT:root},encoding:'utf8',timeout:30000
    });
    assert.equal(child.status,0,child.stdout+'\n'+child.stderr);
    assert.match(child.stdout,/repository discovery/);
  }finally{fs.rmSync(root,{recursive:true,force:true});}
});

test('missing or invalid child exit status cannot mean success',()=>{
  assert.equal(processExitCode(0,null),0);
  assert.equal(processExitCode(2,null),2);
  for(const value of [null,undefined,NaN,-1,256,'0'])assert.notEqual(processExitCode(value,null),0);
  assert.notEqual(processExitCode(0,'UNKNOWN_SIGNAL'),0);
});
test('a real signalled child produces a nonzero execution result',async()=>{
  const {spawn}=require('node:child_process');
  const child=spawn(process.execPath,['-e',"process.kill(process.pid,'SIGTERM')"],{stdio:'ignore'});
  const result=await new Promise((resolve,reject)=>{
    child.once('error',reject);
    child.once('exit',(code,signal)=>resolve({code,signal}));
  });
  assert.equal(result.code,null);
  assert.equal(result.signal,'SIGTERM');
  assert.equal(processExitCode(result.code,result.signal),143);
});
