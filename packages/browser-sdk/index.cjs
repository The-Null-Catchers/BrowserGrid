const {createRequire}=require('node:module');
// Resolve the same physical Playwright installation as the project's test CLI.
const projectRequire=process.env.BG_PROJECT_ROOT?createRequire(require('node:path').join(process.env.BG_PROJECT_ROOT,'package.json')):require;
const base=projectRequire('@playwright/test');
const {capturedPageFixture}=require('./capture.cjs');
const test=base.test.extend({
  page:async({page},use,testInfo)=>capturedPageFixture(page,use,testInfo)
});
module.exports={...base,test};
