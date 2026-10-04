const {createRequire}=require('node:module');
// Resolve the same physical Playwright installation as the project's test CLI.
const projectRequire=process.env.BG_PROJECT_ROOT?createRequire(require('node:path').join(process.env.BG_PROJECT_ROOT,'package.json')):require;
const base=projectRequire('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const test=base.test.extend({
  page:async({page},use,testInfo)=>{
    const consoleEvents=[],networkEvents=[],timing=new Map();
    page.on('console',msg=>{if(consoleEvents.length<1000)consoleEvents.push({type:msg.type(),message:msg.text().slice(0,4000),source:msg.location(),timestamp:Date.now()});});
    page.on('pageerror',error=>{if(consoleEvents.length<1000)consoleEvents.push({type:'pageerror',message:error.message.slice(0,4000),timestamp:Date.now()});});
    page.on('request',request=>{if(timing.size<1000)timing.set(request,Date.now());});
    page.on('requestfinished',async request=>{
      if(networkEvents.length>=1000){timing.delete(request);return;}
      try{
        const response=await request.response();
        const url=new URL(request.url());url.search='';url.hash='';
        networkEvents.push({method:request.method(),url:url.toString(),status:response?.status(),resource_type:request.resourceType(),duration_ms:Date.now()-(timing.get(request)||Date.now()),sizes:await request.sizes()});
      }catch{} finally{timing.delete(request);}
    });
    page.on('requestfailed',request=>{if(networkEvents.length<1000)networkEvents.push({url:request.url().split('?')[0],method:request.method(),resource_type:request.resourceType(),failure:request.failure()?.errorText});timing.delete(request);});
    await use(page);
    for(const [name,content] of [['console.json',consoleEvents],['network.json',networkEvents]]){
      const file=testInfo.outputPath(name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify(content));
      await testInfo.attach(name,{path:file,contentType:'application/json'});
    }
  }
});
module.exports={...base,test};
