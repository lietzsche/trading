// Mock-only browser check. Production is never contacted.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:375,height:812}}),errors=[];
  let blocked=true,posts=0,role='MASTER';
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/api/upbit/auto-orders/reconcile'){
    assert.equal(role,'MASTER');assert.equal(route.request().method(),'POST');posts++;blocked=false;
    return route.fulfill({json:{accepted:1,rejected:0,blocked:0}});
   }
   assert.equal(route.request().method(),'GET','No other mutations or financial orders');
   let body={};
   if(path==='/api/auth/me')body={id:1,user_login_id:'mock',user_name:'검수',user_role:role};
   else if(path==='/api/dashboard')body={auto_on:true,key_registered:true,assets:[],recommendations:[],recent_orders:[],today_orders:[],performance:{},safety:{summary:blocked?'자동매매 일시 중단: 접수 확인되지 않은 주문 1건':'정상',level:blocked?'blocked':'healthy',price_healthy:true,unresolved_orders:blocked?[{identifier:'auto-1-KRW-BTC-BUY-mock-1234567890',market:'KRW-BTC',created_at:'2026-10-05T12:00:00+09:00'}]:[]},notifications:[]};
   else if(path.endsWith('/config'))body={configured:true};
   else if(path.endsWith('/automation'))body={enabled:false,interval_minutes:360};
   else if(path.endsWith('/analyses'))body={items:[],total:0,page:0,page_size:10};
   else body=[];
   await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:5181/');
  fs.mkdirSync('docs/screenshots/work12-guide-2026-10-05',{recursive:true});
  await page.getByRole('heading',{name:'자동매매 일시 중단: 접수 확인되지 않은 주문 1건'}).waitFor();
  const reconcile=page.getByRole('button',{name:'Upbit에서 다시 확인'});
  await reconcile.scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth===document.documentElement.clientWidth),true);
  await page.screenshot({path:'docs/screenshots/work12-guide-2026-10-05/home-blocked-375.png'});
  await reconcile.click();
  await page.getByText('확인 완료 · 접수 1 · 미접수 0 · 미확인 0').waitFor();
  assert.equal(posts,1);
  role='USER';blocked=true;await page.reload();
  await page.getByRole('heading',{name:'자동매매 일시 중단: 접수 확인되지 않은 주문 1건'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Upbit에서 다시 확인'}).count(),0);
  role='MASTER';await page.reload();
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
  console.log('PASS: blocked warning, MASTER lookup-only button, toast/refresh, USER button hidden, six guide sections, horizontal overflow 0, first-visit coach');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
