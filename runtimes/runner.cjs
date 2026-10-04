const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { executionCommand, generatedConfigSource } = require('./config.cjs');
const { chromium, firefox, webkit } = require('@playwright/test');
const emit = (kind, data={}) => console.log('@bg:' + JSON.stringify({kind,...data}));
const state = value => emit('state', {state:value});
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function command(args, cwd, env, code) {
  return new Promise((resolve,reject)=>{
    const child=spawn(args[0],args.slice(1),{cwd,env,stdio:'inherit'});
    child.on('error',reject);
    child.on('exit',(status,signal)=>status===0?resolve():reject(Object.assign(new Error(`${code}: exit ${status}, signal ${signal}`),{code})));
  });
}
(async()=>{
  for(let n=0;!fs.existsSync('/work/ready');n++){
    if(n>=100)throw new Error('Execution input missing');
    await delay(100);
  }
  const input=JSON.parse(fs.readFileSync('/work/input.json','utf8'));
  const config=input.config;
  const source=config.source;
  const env={...process.env,...input.environment};
  fs.mkdirSync('/work/results',{recursive:true});
  if(source.type==='git'){
    state('pulling_source');
    await command(['git','-c','protocol.file.allow=never','init','/work/source'],'/work',env,'REPOSITORY_CLONE_FAILED');
    await command(['git','-c','protocol.file.allow=never','fetch','--depth=1',source.repository,source.commit],'/work/source',env,'REPOSITORY_CLONE_FAILED');
    await command(['git','checkout','--detach','FETCH_HEAD'],'/work/source',env,'REPOSITORY_CLONE_FAILED');
    const sha=fs.readFileSync('/work/source/.git/FETCH_HEAD','utf8').slice(0,40);
    if(sha.toLowerCase()!==source.commit.toLowerCase())throw new Error('Commit mismatch');
  } else if(source.type==='inline'){
    fs.mkdirSync('/work/source/tests',{recursive:true});
    // Inline tests use the instrumentation fixture. Bundles may explicitly import it.
    const code=source.code.replaceAll('"@playwright/test"','"@browsergrid/test"').replaceAll("'@playwright/test'","'@browsergrid/test'");
    fs.writeFileSync('/work/source/tests/inline.spec.ts',code);
  }
  const cwd=path.resolve('/work/source',config.working_directory||'.');
  if(cwd!=='/work/source'&&!cwd.startsWith('/work/source/'))throw new Error('Invalid working directory');
  env.BG_PROJECT_ROOT=cwd;
  state('installing_dependencies');
  if(source.type!=='inline'){
    if(!fs.existsSync(path.join(cwd,'package-lock.json')))throw new Error('Committed package-lock.json required');
    await command(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],cwd,env,'DEPENDENCY_INSTALL_FAILED');
    const installed=require(path.join(cwd,'node_modules/@playwright/test/package.json'));
    if(installed.version!=='1.58.2')throw new Error('Playwright version must match pinned runtime 1.58.2');
  } else {
    fs.symlinkSync('/opt/browsergrid/node_modules',path.join(cwd,'node_modules'),'dir');
  }
  const moduleDir=path.join(cwd,'node_modules/@browsergrid');
  if(source.type!=='inline'){
    fs.mkdirSync(moduleDir,{recursive:true});
    fs.symlinkSync('/opt/browsergrid/sdk',path.join(moduleDir,'test'),'dir');
  }
  const v=config.viewport;
  const generated={testDir:path.join(cwd,'tests'),outputDir:'/work/results/tests',workers:1,retries:config.retries,
    timeout:Math.min(config.timeout_seconds*1000,120000),fullyParallel:false,
    reporter:[['/opt/browsergrid/reporter.cjs'],['json',{outputFile:'/work/results/report.json'}]],
    projects:[{name:config.browser,use:{browserName:config.browser}}],
    use:{viewport:{width:v.width,height:v.height},deviceScaleFactor:v.device_scale_factor,isMobile:v.mobile,hasTouch:v.touch,
      ...(v.user_agent?{userAgent:v.user_agent}:{}),baseURL:config.base_url||undefined,
      screenshot:config.screenshot,video:config.video,trace:config.trace,
      launchOptions:{proxy:{server:process.env.BG_PROXY},chromiumSandbox:true}}};
  // Respect user configuration while forcing BrowserGrid's matrix, reporting and artifacts.
  let userConfig=null;
  for(const name of ['playwright.config.ts','playwright.config.js','playwright.config.mjs','playwright.config.cjs']){
    if(fs.existsSync(path.join(cwd,name))){userConfig=path.join(cwd,name);break;}
  }
  fs.writeFileSync(path.join(cwd,'browsergrid.config.ts'),generatedConfigSource(userConfig,generated));
  state('starting_browser');
  // Verify launch now so a missing runtime is classified as infrastructure failure.
  const engine={chromium,firefox,webkit}[config.browser];
  let browser;
  try {browser=await engine.launch({headless:true,proxy:{server:process.env.BG_PROXY},chromiumSandbox:true});}
  catch(error){error.code='BROWSER_LAUNCH_FAILED';throw error;}
  emit('runtime',{data:{browser_version:browser.version(),playwright:require('@playwright/test/package.json').version}});
  await browser.close();
  state('running');
  const args=[...executionCommand(config.command,cwd,source.type==='inline'),'--config',path.join(cwd,'browsergrid.config.ts')];
  await new Promise((resolve,reject)=>{
    const child=spawn(args[0],args.slice(1),{cwd,env,stdio:'inherit'});
    child.on('error',reject);
    child.on('exit',code=>{process.exitCode=code||0;resolve();});
  });
})().catch(error=>{emit('error',{code:error.code||'RUNTIME_SETUP_FAILED',message:error.message});process.exitCode=2;}).finally(()=>{
  emit('completed',{exit_code:process.exitCode||0});
  process.exitCode=0;
  // Keep tmpfs mounted until the trusted worker retrieves artifacts and removes the container.
  setInterval(()=>{},1000);
});
