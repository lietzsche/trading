// Read-only mock browser verification. Run Vite on 5179 first.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const output=path.resolve('docs/screenshots/us-market-2026-10-03');fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true});
 for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport:{width:375,height:812},colorScheme:theme,serviceWorkers:'block'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   assert.equal(route.request().method(),'GET');const p=new URL(route.request().url()).pathname;let body={};
   if(p==='/api/auth/me')body={id:1,user_role:'MASTER',user_name:'검수',user_login_id:'test'};
   else if(p==='/api/dashboard')body={key_registered:false,auto_on:false,assets:[],notifications:[]};
   else if(p==='/api/recommendations/stock')body=[{code:'US:AAPL',name:'Apple',market_region:'US',currency:'USD',temp_price:120.25,setting_price:100,minimum_selling_price:90,expected_selling_price:130,renewal_cnt:2},{code:'005930',name:'국내 종목',market_region:'KR',currency:'KRW',temp_price:60000,setting_price:50000,minimum_selling_price:45000,expected_selling_price:65000,renewal_cnt:1}];
   else if(p==='/api/dividends')body=[{code:'US:KO',name:'US dividend sample',market_region:'US',currency:'USD',dividend_rate:3,yield_basis:'최근 12개월 지급 배당 / 최근 종가',data_source:'Yahoo Finance',ex_div_date:'2026-09-01',updated_at:'2026-10-03 10:00:00'},{code:'005930',name:'국내 배당 종목',market_region:'KR',dividend_rate:2}];
   else if(p==='/api/admin/errors')body={items:[],page:0,total:0,retention:{days:30,max_records:10000}};
   await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:5179/');await page.locator('.dashboard-hero-card').waitFor();
  const capture=async name=>{await page.waitForTimeout(100);assert(await page.evaluate(()=>document.documentElement.scrollWidth===document.documentElement.clientWidth));await page.screenshot({path:path.join(output,`${theme}-${name}.png`)});};
  await page.locator('.mobile-nav button').nth(2).click();await page.getByText('$120.25',{exact:true}).waitFor();
  await page.getByRole('button',{name:'미국 1',exact:true}).click();assert.equal(await page.locator('.recommendation').count(),1);await page.getByText('미국 · USD',{exact:true}).waitFor();await capture('stock-us');
  await page.getByRole('button',{name:'국내 1',exact:true}).click();await page.getByText('60,000원',{exact:true}).waitFor();
  await page.getByRole('button',{name:'더보기',exact:true}).click();await page.getByRole('button',{name:'배당주',exact:true}).click();await page.getByRole('button',{name:'미국 1',exact:true}).click();assert.equal(await page.locator('.dividend').count(),1);await page.getByText('3%',{exact:true}).waitFor();await capture('dividend-us');
  await page.getByRole('button',{name:'더보기',exact:true}).click();await page.getByRole('button',{name:'오류',exact:true}).click();await page.getByText(/오류 기록은 30일 보존/).waitFor();await capture('retention');
  assert.deepEqual(errors,[]);await page.close();
 }
 await browser.close();console.log('PASS: US/KR stock and dividend filters, dollar/won prices, error-retention notice and mobile overflow.');
})().catch(e=>{console.error(e);process.exit(1)});
