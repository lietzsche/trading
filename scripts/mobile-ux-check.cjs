/* Mock-only browser regression: never sends financial requests to a real server.
 * Start Vite on 5179, then PLAYWRIGHT_MODULE=/path/to/playwright node scripts/mobile-ux-check.cjs.
 */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const output=path.resolve('docs/screenshots/mobile-chat-followup-2026-10-03');
const user={id:7,user_role:'MASTER',user_name:'모바일 검수',user_login_id:'demo',user_email:'demo@example.org'};
const settings={expected_high_percentage:20,expected_low_percentage:-10,highest_price_reference_days:30,volume_check:false};
const items=Array.from({length:23},(_,i)=>({id:23-i,status:'COMPLETED',market:'upbit',prompt:`계좌 검토 ${23-i}`,created_at:'2026-10-03T00:00:00Z',has_running_message:i===3,automation_run:i%2===0}));
items[1].applied_candidate_id='applied-candidate';
const result={report:'## 결론\n현재 설정을 유지하세요.\n\n- 목표 상승률 **20%**, 손절 폭 **10%**\n- 과거 검증은 미래 수익을 보장하지 않습니다.',decisions:[{code:'KRW-BTC',action:'HOLD',reason:'현재 손절 기준을 이탈하지 않았습니다.',confidence:70}],candidates:[{id:'baseline',label:'현재 설정',settings,validation:{return_pct:5,max_drawdown_pct:5.93,trades:5,days:30}}],warnings:['과거 검증이며 미래 수익을 보장하지 않습니다.']};
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true}); const report={};
 for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width:375,height:812},serviceWorkers:'block'});
  await context.addInitScript(theme=>{localStorage.setItem('theme',theme);localStorage.setItem('ai-disclaimer-closed','true');},theme);
  await context.addInitScript(()=>{window.scrollRequests=[];const original=Element.prototype.scrollIntoView;Element.prototype.scrollIntoView=function(...args){window.scrollRequests.push(this.id);return original.apply(this,args)}});
  const page=await context.newPage();let auto=false,simulateReply=false,replyAnswer='현재 손절 폭 **10%**를 유지하세요. 시장 변동을 다시 확인하세요.';const calls=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname;let body={};
   if(p==='/api/auth/me'||p==='/api/profile')body=user;
   else if(p==='/api/upbit/key/status')body={registered:true};
   else if(p==='/api/upbit/auto'){assert.equal(request.method(),'PUT');calls.push(request.postDataJSON());auto=request.postDataJSON().auto_on;body={ok:true};}
   else if(p==='/api/dashboard')body={key_registered:true,auto_on:auto,total_valuation:1250000,available_krw:100000,assets:[{currency:'KRW',balance:100000,locked:0},{currency:'BTC',balance:.01,locked:0,avg_buy_price:100000000,current_price:115000000,valuation:1150000,profit_rate:15}],notifications:[],holdings:[]};
   else if(p.includes('/recommendations/'))body=[{code:'KRW-BTC',name:'비트코인',temp_price:115000000,setting_price:100000000,expected_selling_price:120000000,minimum_selling_price:90000000,renewal_cnt:2,owned:true,owned_quantity:.01,updated_at:new Date().toISOString()},{code:'KRW-ETH',name:'이더리움',temp_price:4500000,setting_price:4000000,expected_selling_price:4800000,minimum_selling_price:3600000,renewal_cnt:1,owned:false,updated_at:new Date().toISOString()}];
   else if(p.endsWith('/config'))body={configured:true,model:'deepseek-flash',key_hint:'검수 키'};
   else if(p.endsWith('/automation'))body={enabled:true,interval_minutes:360,trigger_mode:'interval',auto_apply_settings:true};
   else if(p.endsWith('/analyses')){const index=Number(url.searchParams.get('page')||0);body={items:items.slice(index*10,index*10+10),page:index,page_size:10,total:23};}
   else if(/\/analyses\/\d+$/.test(p)){body={...items.find(i=>i.id===Number(p.split('/').at(-1))),include_account:true,settings_snapshot:settings,result,conversations:[{id:1,status:simulateReply?'RUNNING':'COMPLETED',question:'손절 폭은 유지할까요?',answer:simulateReply?null:replyAnswer,usage_tokens:100}]};simulateReply=false;}
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
  assert.equal(await page.locator('.ai-compact-consent [role="switch"]').getAttribute('aria-checked'),'false');
  await page.getByRole('button',{name:'AI 설정',exact:true}).click();await capture('ai-settings');await page.keyboard.press('Escape');assert.equal(await page.getByRole('button',{name:'AI 설정',exact:true}).evaluate(el=>el===document.activeElement),true);
  await page.locator('.ai-chat-list-button').click();await page.getByRole('dialog',{name:'AI 대화 목록'}).waitFor();
  await page.getByRole('button',{name:'선택',exact:true}).click();assert.equal(await page.locator('.ai-message-composer').isVisible(),false);
  await page.locator('.ai-history-item-btn').first().click();assert.equal(await page.locator('.ai-history-check input').first().isChecked(),true);assert.equal(await page.locator('.ai-history-check input').nth(3).isDisabled(),true);
  await page.keyboard.press('Escape');
  await page.locator('.ai-chat-list-button').click();await page.locator('.ai-history-item-btn').nth(1).click();await page.getByRole('button',{name:'대화 메뉴',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'목록에서 숨기기',exact:true}).waitFor();await page.getByRole('dialog').getByRole('button',{name:'적용 전 설정으로 되돌리기',exact:true}).waitFor();assert.equal(await page.getByRole('dialog').getByRole('button',{name:'대화 삭제',exact:true}).count(),0);await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'더보기',exact:true}).click();await capture('more');
  await page.getByRole('button',{name:'연결 관리',exact:true}).click();await page.locator('#connection-management').waitFor();await page.evaluate(()=>window.scrollTo(0,0));await capture('connections');
  const directScrolls=await page.evaluate(()=>window.scrollRequests.filter(id=>id==='connection-management').length);assert.equal(directScrolls,1);
  await page.locator('.mobile-nav button').first().click();await page.getByRole('button',{name:'더보기',exact:true}).click();await page.getByRole('button',{name:'내 정보',exact:true}).click();await page.locator('#connection-management').waitFor();
  assert.equal(await page.evaluate(()=>window.scrollRequests.filter(id=>id==='connection-management').length),directScrolls);
  console.log('PASS: connections_request_consumed_on_remount',theme);
  await page.getByRole('button',{name:'더보기',exact:true}).click();await page.getByRole('dialog',{name:'더보기'}).getByRole('button',{name:'AI 설정',exact:true}).click();await page.getByRole('dialog',{name:'AI 설정'}).waitFor();
  assert.equal(await page.getByRole('dialog',{name:'AI 설정'}).count(),1);await page.keyboard.press('Escape');await page.locator('.mobile-nav button').first().click();await page.locator('.mobile-nav button').nth(3).click();await page.locator('.ai-result').waitFor();assert.equal(await page.getByRole('dialog',{name:'AI 설정'}).count(),0);
  console.log('PASS: ai_settings_request_consumed_on_remount',theme);
  for(const size of [{width:375,height:812},{width:360,height:740}])for(const visit of ['first','returning']){
   await page.evaluate(visit=>{if(visit==='first')localStorage.clear();else localStorage.setItem('ai-disclaimer-closed','true')},visit);
   await page.locator('.mobile-nav button').first().click();await page.locator('.mobile-nav button').nth(3).click();await page.locator('.ai-result').waitFor();await page.setViewportSize(size);await page.getByRole('button',{name:'AI 대화',exact:true}).click();await page.waitForTimeout(200);
   const name=`chat-${visit}-${size.width}`;await capture(name);
   const measurement=await page.evaluate(()=>{const thread=document.querySelector('.ai-chat-thread').getBoundingClientRect(),composer=document.querySelector('.ai-compact-composer').getBoundingClientRect(),nav=document.querySelector('.mobile-nav').getBoundingClientRect(),root=document.documentElement;return {threadHeight:thread.height,composerTop:composer.top,composerBottom:composer.bottom,composerHeight:composer.height,navTop:nav.top,scrollHeight:root.scrollHeight,clientHeight:root.clientHeight}});
   Object.assign(report[`${theme}-${name}`],measurement);assert(measurement.threadHeight>=(size.width===375?400:320));assert(measurement.composerHeight<=110);assert(measurement.composerBottom<=measurement.navTop);assert.equal(measurement.scrollHeight,measurement.clientHeight);
   await page.getByRole('button',{name:'투자 위험 안내',exact:true}).click();await page.getByRole('dialog').getByText('수익 예측이 아닌 과거 데이터 검증입니다.',{exact:true}).waitFor();await page.keyboard.press('Escape');
   await page.getByRole('button',{name:'계좌 전송 항목 안내',exact:true}).click();await page.getByRole('dialog',{name:'무엇이 전송되나요?'}).waitFor();await page.keyboard.press('Escape');
  }
  await page.setViewportSize({width:375,height:812});
  simulateReply=true;replyAnswer=('추가 시장 자료를 확인했습니다.\n\n').repeat(30)+'마지막 답변';
  await page.locator('.mobile-nav button').first().click();await page.locator('.mobile-nav button').nth(3).click();await page.locator('.ai-result').waitFor();await page.getByRole('button',{name:'AI 대화',exact:true}).click();
  await page.locator('.ai-chat-thread').evaluate(el=>{el.scrollTop=0});await page.getByText('마지막 답변',{exact:true}).waitFor();await page.waitForTimeout(100);
  assert(await page.locator('.ai-chat-thread').evaluate(el=>Math.abs(el.scrollHeight-el.clientHeight-el.scrollTop)<2),'New reply scrolls to bottom');console.log('PASS: new_reply_polling_scrolls_to_bottom',theme);
  await page.locator('.ai-chat-thread').evaluate(el=>{el.scrollTop=0});
  await page.getByRole('button',{name:'판단 요약',exact:true}).click();await page.getByRole('button',{name:'AI 대화',exact:true}).click();await page.waitForTimeout(100);
  assert(await page.locator('.ai-chat-thread').evaluate(el=>Math.abs(el.scrollHeight-el.clientHeight-el.scrollTop)<2),'Chat bottom after layout');
  await page.locator('.ai-compact-input textarea').fill('첫 줄\n둘째 줄\n셋째 줄\n넷째 줄\n다섯째 줄');await page.waitForTimeout(100);
  assert.equal(await page.locator('.ai-compact-input textarea').evaluate(el=>el.getBoundingClientRect().height),96);
  await page.locator('.ai-compact-input textarea').fill('');
  await page.evaluate(()=>{Object.defineProperty(window.visualViewport,'height',{configurable:true,value:400});window.visualViewport.dispatchEvent(new Event('resize'))});await page.locator('.ai-compact-input textarea').focus();await page.waitForTimeout(150);
  const keyboard=await page.evaluate(()=>({threadHeight:document.querySelector('.ai-chat-thread').clientHeight,composerBottom:document.querySelector('.ai-compact-composer').getBoundingClientRect().bottom,keyboardOpen:document.querySelector('.ai-page').dataset.keyboardOpen}));
  assert.equal(keyboard.keyboardOpen,'true');assert(keyboard.threadHeight>=120);assert(keyboard.composerBottom<=400);report[`${theme}-keyboard-simulated`]=keyboard;
  await page.locator('.ai-compact-input textarea').blur();await page.evaluate(()=>{delete window.visualViewport.height;window.visualViewport.dispatchEvent(new Event('resize'))});await page.waitForTimeout(100);
  await page.locator('.mobile-nav button').first().click();
  await page.evaluate(()=>{window.originalViewport=window.visualViewport;Object.defineProperty(window,'visualViewport',{configurable:true,value:undefined})});
  await page.locator('.mobile-nav button').nth(3).click();await page.locator('.ai-result').waitFor();await page.getByRole('button',{name:'AI 대화',exact:true}).click();await page.waitForTimeout(100);
  assert(await page.locator('.ai-chat-thread').evaluate(el=>el.clientHeight>=400));
  await page.locator('.mobile-nav button').first().click();await page.evaluate(()=>{Object.defineProperty(window,'visualViewport',{configurable:true,value:window.originalViewport});delete window.originalViewport});
  await page.evaluate(()=>localStorage.removeItem('ai-disclaimer-closed'));
  await page.locator('.mobile-nav button').first().click();
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
 await browser.close();fs.writeFileSync(path.join(output,'metrics.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));console.log('PASS: one-shot navigation, compact chat dimensions, consent and protection, mock visualViewport, desktop layout and screenshots.');
})().catch(e=>{console.error(e);process.exit(1)});
