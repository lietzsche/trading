// Mock-only browser check. Production is never contacted.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:375,height:812}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',async route=>{
   assert.equal(route.request().method(),'GET');
   const path=new URL(route.request().url()).pathname;
   let body={};
   if(path==='/api/auth/me')body={id:1,user_login_id:'mock',user_name:'검수',user_role:'MASTER'};
   else if(path==='/api/dashboard')body={assets:[],recommendations:[],recent_orders:[],today_orders:[],performance:{},safety:{summary:'모의 검수',level:'neutral'},notifications:[]};
   else if(path.endsWith('/config'))body={configured:true};
   else if(path.endsWith('/automation'))body={enabled:false,interval_minutes:360};
   else if(path.endsWith('/analyses'))body={items:[],total:0,page:0,page_size:10};
   else body=[];
   await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:5181/');
  await page.getByRole('button',{name:'더보기',exact:true}).click();
  await page.getByRole('button',{name:'사용 안내',exact:true}).click();
  await page.getByRole('heading',{name:'사용 안내',exact:true}).waitFor();
  assert.equal(await page.locator('main details').count(),6);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth===document.documentElement.clientWidth),true);
  fs.mkdirSync('docs/screenshots/work12-guide-2026-10-05',{recursive:true});
  await page.screenshot({path:'docs/screenshots/work12-guide-2026-10-05/usage-guide-375.png'});
  await page.getByRole('button',{name:'AI',exact:true}).click();
  await page.getByRole('heading',{name:'여기서 할 수 있는 일'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'사용 안내 보기'}).count(),1);
  await page.getByRole('button',{name:'사용 안내 보기'}).click();
  await page.getByRole('button',{name:'AI',exact:true}).click();
  await page.getByRole('heading',{name:'투자 판단',exact:true}).waitFor();
  assert.equal(await page.getByRole('heading',{name:'여기서 할 수 있는 일'}).count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS: six sections, no horizontal overflow, configured-key first-visit coach, revisit hidden');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
