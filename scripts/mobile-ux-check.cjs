/* Mock-only browser regression: never sends financial requests to a real server.
 * Start Vite on 5179, then PLAYWRIGHT_MODULE=/path/to/playwright node scripts/mobile-ux-check.cjs.
 */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const output=path.resolve('docs/screenshots/mobile-ux-2026-10-03');
const user={id:7,user_role:'MASTER',user_name:'모바일 검수',user_login_id:'demo',user_email:'demo@example.org'};
const settings={expected_high_percentage:20,expected_low_percentage:-10,highest_price_reference_days:30,volume_check:false};
const items=Array.from({length:23},(_,i)=>({id:23-i,status:'COMPLETED',market:'upbit',prompt:`계좌 검토 ${23-i}`,created_at:'2026-10-03T00:00:00Z',has_running_message:i===3,automation_run:i%2===0}));
const result={report:'## 결론\n현재 설정을 유지하세요.\n\n- 목표 상승률 **20%**, 손절 폭 **10%**\n- 과거 검증은 미래 수익을 보장하지 않습니다.',decisions:[{code:'KRW-BTC',action:'HOLD',reason:'현재 손절 기준을 이탈하지 않았습니다.',confidence:70}],candidates:[{id:'baseline',label:'현재 설정',settings,validation:{return_pct:5,max_drawdown_pct:5.93,trades:5,days:30}}],warnings:['과거 검증이며 미래 수익을 보장하지 않습니다.']};
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true}); const report={};
 for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width:375,height:812},serviceWorkers:'block'});
  await context.addInitScript(theme=>{localStorage.setItem('theme',theme);localStorage.setItem('ai-disclaimer-closed','true');},theme);
  const page=await context.newPage();let auto=false;const calls=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname;let body={};
   if(p==='/api/auth/me'||p==='/api/profile')body=user;
   else if(p==='/api/upbit/auto'){assert.equal(request.method(),'PUT');calls.push(request.postDataJSON());auto=request.postDataJSON().auto_on;body={ok:true};}
   else if(p==='/api/dashboard')body={key_registered:true,auto_on:auto,total_valuation:1250000,available_krw:100000,assets:[{currency:'KRW',balance:100000,locked:0},{currency:'BTC',balance:.01,locked:0,avg_buy_price:100000000,current_price:115000000,valuation:1150000,profit_rate:15}],notifications:[],holdings:[]};
   else if(p.includes('/recommendations/'))body=[{code:'KRW-BTC',name:'비트코인',temp_price:115000000,setting_price:100000000,expected_selling_price:120000000,minimum_selling_price:90000000,renewal_cnt:2,owned:true,owned_quantity:.01,updated_at:new Date().toISOString()},{code:'KRW-ETH',name:'이더리움',temp_price:4500000,setting_price:4000000,expected_selling_price:4800000,minimum_selling_price:3600000,renewal_cnt:1,owned:false,updated_at:new Date().toISOString()}];
   else if(p.endsWith('/config'))body={configured:true,model:'deepseek-flash',key_hint:'검수 키'};
   else if(p.endsWith('/automation'))body={enabled:true,interval_minutes:360,trigger_mode:'interval',auto_apply_settings:true};
   else if(p.endsWith('/analyses')){const index=Number(url.searchParams.get('page')||0);body={items:items.slice(index*10,index*10+10),page:index,page_size:10,total:23};}
   else if(/\/analyses\/\d+$/.test(p))body={...items.find(i=>i.id===Number(p.split('/').at(-1))),include_account:true,settings_snapshot:settings,result,conversations:[{id:1,status:'COMPLETED',question:'손절 폭은 유지할까요?',answer:'현재 손절 폭 **10%**를 유지하세요. 시장 변동을 다시 확인하세요.',usage_tokens:100}]};
   else if(p.endsWith('/settings'))body=[];
   else if(request.method()!=='GET')throw new Error(`Unexpected mutation: ${request.method()} ${p}`);
   await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:5179/');await page.getByRole('switch',{name:'자동매매',exact:true}).waitFor();
  const capture=async name=>{
   await page.waitForTimeout(200);
   const metrics=await page.evaluate(()=>{
    const root=document.documentElement,header=document.querySelector('main>header'),composer=document.querySelector('.ai-message-composer');
    const dialog=document.querySelector('[role="dialog"]'),scope=dialog||document.querySelector('.layout');
    const small=[...scope.querySelectorAll('button,summary,input,select,textarea,a,[role="slider"]')].filter(el=>{
     if(!el.checkVisibility({checkVisibilityCSS:true}))return false;
     const rect=el.getBoundingClientRect();
     const label=el.matches('input[type="checkbox"]')?el.closest('label'):null;const target=(label||el).getBoundingClientRect();
     return target.width<43.9||target.height<43.9;
    }).map(el=>({text:el.getAttribute('aria-label')||el.textContent?.trim().slice(0,40)||el.tagName,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
    return {headerHeight:header?.getBoundingClientRect().height,composerY:composer?.getBoundingClientRect().top,scrollWidth:root.scrollWidth,clientWidth:root.clientWidth,smallTargets:small};
   });report[`${theme}-${name}`]=metrics;
   assert.equal(metrics.scrollWidth,metrics.clientWidth,`${theme}-${name}: horizontal overflow`);
   assert(metrics.headerHeight<=120,`${name}: header too high`);
   assert.equal(metrics.smallTargets.length,0,`${theme}-${name}: small touch target`);
   await page.screenshot({path:path.join(output,`${theme}-${name}.png`)});
  };
  await capture('home');
  await page.getByRole('switch',{name:'자동매매',exact:true}).click();assert.equal(calls.length,0);
  await page.getByRole('dialog').getByText('추천 1순위 종목에 원화 잔고 전액으로 시장가 매수할 수 있습니다.',{exact:true}).waitFor();
  await capture('auto-confirm');
  const slider=page.getByRole('slider');await slider.focus();await slider.press('Enter');assert.equal(calls.length,0);
  await page.keyboard.press('Escape');assert.equal(calls.length,0);
  await page.getByRole('switch',{name:'자동매매',exact:true}).click();await slider.focus();
  for(let i=0;i<18;i++)await slider.press('ArrowRight');await slider.press('Enter');
  await page.waitForFunction(()=>document.querySelector('[role="switch"]')?.getAttribute('aria-checked')==='true');
  assert.deepEqual(calls,[{auto_on:true}]);
  await page.getByRole('switch',{name:'자동매매',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role="switch"]')?.getAttribute('aria-checked')==='false');assert.deepEqual(calls,[{auto_on:true},{auto_on:false}]);
  await page.locator('.mobile-nav button').nth(1).click();await page.getByText('비트코인',{exact:true}).first().waitFor();await capture('upbit');
  await page.locator('.mobile-nav button').nth(3).click();await page.locator('.ai-result').waitFor();await capture('ai-summary');
  await page.getByRole('button',{name:'AI 대화',exact:true}).click();await page.locator('.ai-message-composer').waitFor();await page.evaluate(()=>window.scrollTo(0,0));await capture('ai-chat');
  const composer=await page.locator('.ai-message-composer').boundingBox(),nav=await page.locator('.mobile-nav').boundingBox();
  assert(composer.y+composer.height<=nav.y,`${theme}: composer obscured by navigation`);
  assert(await page.locator('.ai-chat-thread').evaluate(el=>el.scrollHeight>el.clientHeight),'Chat needs internal scrolling');
  assert.equal(await page.locator('.ai-chat-consent-row input').isChecked(),false);
  await page.getByRole('button',{name:'AI 설정',exact:true}).click();await capture('ai-settings');await page.keyboard.press('Escape');assert.equal(await page.getByRole('button',{name:'AI 설정',exact:true}).evaluate(el=>el===document.activeElement),true);
  await page.locator('.ai-list-trigger').click();await page.getByRole('dialog',{name:'AI 대화 목록'}).waitFor();
  await page.getByRole('button',{name:'선택',exact:true}).click();assert.equal(await page.locator('.ai-message-composer').isVisible(),false);
  await page.locator('.ai-history-item-btn').first().click();assert.equal(await page.locator('.ai-history-check input').first().isChecked(),true);assert.equal(await page.locator('.ai-history-check input').nth(3).isDisabled(),true);
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'더보기',exact:true}).click();await capture('more');
  await page.getByRole('button',{name:'연결 관리',exact:true}).click();await page.locator('#connection-management').waitFor();await page.evaluate(()=>window.scrollTo(0,0));await capture('connections');
  await page.evaluate(()=>localStorage.removeItem('ai-disclaimer-closed'));
  await page.locator('.mobile-nav button').nth(3).click();await page.locator('.ai-disclaimer').waitFor();
  assert.equal(await page.locator('.ai-disclaimer').getAttribute('open'),'');
  await page.locator('.ai-disclaimer summary').click();await page.waitForFunction(()=>localStorage.getItem('ai-disclaimer-closed')==='true');
  await page.setViewportSize({width:1440,height:900});await page.getByRole('button',{name:'AI 설정',exact:true}).click();
  assert.equal(await page.locator('.ai-settings-panel[role="dialog"]').count(),0);
  assert.equal(await page.locator('.ai-chat-workspace').evaluate(el=>getComputedStyle(el).display),'grid');
  user.user_role='USER';await page.reload();await page.locator('.dashboard-hero-card').waitFor();
  assert.equal(await page.locator('.desktop-nav button').filter({hasText:'AI 분석'}).count(),0);
  assert.equal(await page.locator('.desktop-nav button').filter({hasText:'계산 설정'}).count(),0);
  user.user_role='MASTER';
  assert.deepEqual(errors,[]);await context.close();
 }
 await browser.close();fs.writeFileSync(path.join(output,'metrics.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));console.log('PASS: confirmation gate, immediate disable, focus restore, consent, mobile selection and 16 screenshots.');
})().catch(e=>{console.error(e);process.exit(1)});
