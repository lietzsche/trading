// Mock-only auth UI checks. No login or financial requests reach production.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const enabled of [false,true]){
   const page=await browser.newPage({viewport:{width:375,height:812}});
   await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    assert.equal(route.request().method(),'GET','Only read-only mock requests allowed');
    if(path==='/api/auth/config')return route.fulfill({json:{signup_enabled:enabled}});
    return route.fulfill({status:401,json:{detail:'로그인이 필요합니다.'}});
   });
   await page.goto('http://127.0.0.1:5181/');
   await page.getByRole('button',{name:'로그인',exact:true}).waitFor();
   await page.waitForTimeout(200);
   assert.equal(await page.getByRole('button',{name:'처음이신가요? 계정 만들기'}).count(),enabled?1:0);
   await page.close();
  }
  console.log('PASS: 375x812 signup disabled hides button; enabled exposes button; GET-only mocks');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
