import React, {useCallback, useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api, createRequestGate, orderStatus} from './api';
import AIAnalysis from './AIAnalysis';
import './style.css';
import './sell.css';
import './pwa.css';
import './pagination.css';
import './review.css';
import './theme.css';
import './mobile-improvements.css';
import './dashboard.css';

if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));

const labels={code:'종목 코드',name:'종목명',minimum_selling_price:'손절가',expected_selling_price:'목표가',origin_minimum_selling_price:'최초 손절가',origin_expected_selling_price:'최초 목표가',temp_price:'현재가',setting_price:'기준가',renewal_cnt:'갱신 단계',pricing_reference_date:'기준 갱신 시각',updated_at:'최근 확인 시각',dividend_rate:'배당수익률',ex_div_date:'배당락일',pay_date:'지급일',uuid:'주문 번호',side:'구분',ord_type:'주문 방식',price:'주문 가격',state:'상태',market:'마켓',created_at:'일시',volume:'주문 수량',executed_volume:'체결 수량',currency:'자산',balance:'주문 가능',quantity:'총 보유량',locked:'주문 중',avg_buy_price:'평균 매수가',current_price:'현재가',valuation:'평가금액',purchase_amount:'매수금액',profit_rate:'수익률',avg_buy_price_modified:'평균가 수정',unit_currency:'기준 통화',id:'번호',source:'구분',operation:'작업',error_type:'오류 종류',message:'내용',user_login_id:'아이디',user_name:'이름',user_role:'권한',user_email:'이메일',deleted:'비활성',email:'이메일 주소',status:'전체 상태',database:'데이터베이스',calculation:'계산 서비스',api_uptime_seconds:'API 가동 시간',error_count:'누적 오류',trading_execution:'자동 실행',scheduler_running:'스케줄러',key_registered:'API 키 등록',auto_on:'자동매매'};
const stateLabels={bid:'매수',ask:'매도',done:'체결 완료',wait:'체결 대기',cancel:'취소',watch:'예약 주문',market:'시장가',limit:'지정가',price:'시장가 매수',UP:'정상',DOWN:'중단',ACTIVE:'사용 중',DISABLED:'사용 안 함',FETCH_PRICE:'종목 가격 조회',AUTO_ORDER:'자동매매',SCHEDULE_UPDATE:'추천 가격 갱신',SAVE_HISTORY_ITEM:'가격 이력 저장',SYNC_ORDER_HISTORY:'주문 내역 동기화',RECOMMENDATION_BALANCE:'보유 종목 확인',ConnectError:'네트워크 연결 실패',HTTPStatusError:'외부 API 응답 오류'};
const priceKeys=new Set(['minimum_selling_price','expected_selling_price','origin_minimum_selling_price','origin_expected_selling_price','temp_price','setting_price','price','avg_buy_price','current_price','valuation','purchase_amount']);
const dateKeys=new Set(['pricing_reference_date','updated_at','created_at','ex_div_date','pay_date']);
const number=(value,digits=2)=>Number(value).toLocaleString('ko-KR',{maximumFractionDigits:digits});
const signed=value=>`${value>0?'+':''}${number(value)}%`;
function formatKrw(val){if(val==null||val==='')return '—';const num=Number(val);if(isNaN(num))return String(val);return `₩ ${Math.round(num).toLocaleString('ko-KR')}`;}
function formatPrice(val){if(val==null||val==='')return '—';const num=Number(val);if(isNaN(num))return String(val);if(num>=1000)return `${Math.round(num).toLocaleString('ko-KR')}원`;if(num>=100)return `${Number(num.toFixed(1)).toLocaleString('ko-KR')}원`;if(num>=1)return `${Number(num.toFixed(2)).toLocaleString('ko-KR')}원`;return `${Number(num.toFixed(4)).toLocaleString('ko-KR')}원`;}
function formatQty(val,currency=''){if(val==null||val==='')return '0';const num=Number(val);if(isNaN(num))return String(val);const formatted=num.toLocaleString('ko-KR',{maximumFractionDigits:6});return currency?`${formatted} ${currency}`:formatted;}
function display(key,value){if(value===null||value===undefined||value==='')return '—';if(typeof value==='boolean')return value?'예':'아니오';if(['dividend_rate','profit_rate'].includes(key))return `${number(value)}%`;if(key==='api_uptime_seconds'){const hours=Math.floor(value/3600),minutes=Math.floor(value%3600/60);return `${hours}시간 ${minutes}분`}if(priceKeys.has(key))return number(value,8);if(dateKeys.has(key))return String(value).replace('T',' ').slice(0,16);return stateLabels[value]??String(value)}

const tabs=[['account','오늘의 대시보드','홈'],['upbit','Upbit 추천','코인'],['stock','주식 추천','주식'],['dividends','배당주','배당'],['orders','주문 내역','주문'],['ai','AI 분석','AI'],['profile','내 정보','정보'],['system','시스템','상태'],['errors','오류','오류'],['autos','자동매매','자동'],['settings','계산 설정','설정'],['users','사용자','사용자'],['mail','메일','메일']];

function Login({onLogin,message}){const [loginId,setLoginId]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[joining,setJoining]=useState(false),[name,setName]=useState('');async function submit(event){event.preventDefault();setError('');try{if(joining){await api('/auth/join',{method:'POST',body:JSON.stringify({login_id:loginId,password,name})});setJoining(false);setPassword('');return}await api('/auth/login',{method:'POST',body:JSON.stringify({login_id:loginId,password})});onLogin()}catch(e){setError(e.message)}}return <main className="login"><section className="login-shell"><div className="login-intro"><img src="/icons/icon-192.png" alt="Trading"/><small className="eyebrow">PERSONAL TRADING DESK</small><h1>내 투자 흐름을<br/>한눈에 확인하세요.</h1><p>추천 종목, 보유 자산과 자동매매 상태를 안전하게 관리합니다.</p></div><form className="login-form" onSubmit={submit}><div><h2>{joining?'새 계정 만들기':'로그인'}</h2><p>{joining?'필요한 정보만 입력해 시작하세요.':'계속하려면 계정 정보를 입력하세요.'}</p></div>{joining&&<label>이름<input value={name} onChange={e=>setName(e.target.value)} required autoComplete="name"/></label>}<label>아이디<input autoFocus value={loginId} onChange={e=>setLoginId(e.target.value)} required autoComplete="username"/></label><label>비밀번호<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required autoComplete={joining?'new-password':'current-password'}/></label>{(error||message)&&<div className="error" role="alert">{error||message}</div>}<button className="primary">{joining?'계정 만들기':'로그인'}</button><button type="button" className="text-button" onClick={()=>{setJoining(!joining);setError('')}}>{joining?'이미 계정이 있나요? 로그인':'처음이신가요? 계정 만들기'}</button></form></section></main>}
function Empty({text='표시할 데이터가 없습니다.'}){return <div className="empty"><b>아직 데이터가 없습니다</b><span>{text}</span></div>}
function usePagination(rows,size){const [page,setPage]=useState(0),pages=Math.max(1,Math.ceil((rows?.length||0)/size));useEffect(()=>setPage(value=>Math.min(value,pages-1)),[pages]);return {page,setPage,pages,items:(rows||[]).slice(page*size,(page+1)*size)}}
function Pager({page,pages,onChange}){if(pages<=1)return null;return <nav className="pager" aria-label="페이지 이동"><button className="quiet" disabled={page===0} onClick={()=>onChange(page-1)}>이전</button><span><b>{page+1}</b> / {pages}</span><button className="quiet" disabled={page+1===pages} onClick={()=>onChange(page+1)}>다음</button></nav>}
function Table({rows,columns}){if(!Array.isArray(rows)||!rows.length)return <Empty/>;const keys=columns||Object.keys(rows[0]);return <div className="table-wrap"><table><thead><tr>{keys.map(key=><th key={key}>{labels[key]||key}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={row.id??row.uuid??row.code??index}>{keys.map(key=><td data-label={labels[key]||key} key={key}>{display(key,row[key])}</td>)}</tr>)}</tbody></table></div>}

function PriceFreshness({rows}) {
 const [,setTick]=useState(0);
 useEffect(()=>{const timer=setInterval(()=>setTick(value=>value+1),15000);return()=>clearInterval(timer)},[]);
 const latest=(rows||[]).map(row=>row.updated_at).filter(Boolean).sort().at(-1);
 if(!latest)return <div className="price-freshness unknown"><span>가격 갱신 시각 확인 불가</span></div>;
 const parsed=new Date(String(latest).replace(' ','T')),age=Date.now()-parsed.getTime(),healthy=Number.isFinite(age)&&age<=150000;
 return <div className={`price-freshness ${healthy?'healthy':'delayed'}`} role="status"><span><i/>{healthy?'가격 갱신 정상':'가격 갱신 지연'} · {display('updated_at',latest)}</span><details><summary aria-label="가격 갱신 주기 안내">?</summary><p>Upbit 추천 가격은 서버가 1분마다 갱신하고, 이 화면은 열려 있는 동안 30초마다 결과를 확인합니다. 자동 주문 판단은 별도로 30초마다 실행됩니다.</p></details></div>;
}
function RecommendationCards({rows,market,onAskAI}) {
 const [ownedOnly,setOwnedOnly]=useState(false),ownedRows=(rows||[]).filter(row=>row.owned===true),visibleRows=ownedOnly?ownedRows:rows;
 const pagination=usePagination(visibleRows,9);
 if(!rows?.length)return <Empty text="다음 수집 주기에 조건에 맞는 종목이 자동으로 추가됩니다."/>;
 return (
  <>
   {market==='upbit'&&<PriceFreshness rows={rows}/>}
   <div className="recommendation-toolbar">
    <p className="summary">갱신 단계 우선 · 같은 단계는 목표 도달률 순</p>
    {market==='upbit'&&rows.some(row=>typeof row.owned==='boolean')&&(
     <div className="filter-chips" aria-label="추천 종목 필터">
      <button className={!ownedOnly?'active':''} aria-pressed={!ownedOnly} onClick={()=>setOwnedOnly(false)}>전체 {rows.length}</button>
      <button className={ownedOnly?'active':''} aria-pressed={ownedOnly} onClick={()=>setOwnedOnly(true)}>내 보유 {ownedRows.length}</button>
     </div>
    )}
   </div>
   {ownedOnly&&!visibleRows.length?<Empty text="현재 추천 목록에 보유 중인 종목이 없습니다."/>:(
    <>
     <div className="recommendations">
      {pagination.items.map(row=>{
       const range=Number(row.expected_selling_price)-Number(row.minimum_selling_price);
       const progress=range?100-(Number(row.expected_selling_price)-Number(row.temp_price))*100/range:0;
       const change=Number(row.setting_price)?(Number(row.temp_price)-Number(row.setting_price))*100/Number(row.setting_price):0;
       const visual=Math.max(0,Math.min(100,progress));
       return (
        <article className={`recommendation ${row.owned?'owned':''}`} key={row.code}>
         <div className="recommendation-head">
          <div>
           <div className="tag-row">
            <span className={`market ${market}`}>{market==='upbit'?'UPBIT':'STOCK'}</span>
            {row.owned&&<span className="owned-badge">보유 중 · {formatQty(row.owned_quantity)}</span>}
           </div>
           <h3>{row.name}</h3>
           <small>{row.code}</small>
          </div>
          <div className={`change ${change>=0?'up':'down'}`}>
           <small>기준가 대비</small>
           <strong>{signed(change)}</strong>
          </div>
         </div>
         <div className="price-main">
          <small>현재가</small>
          <strong>{formatPrice(row.temp_price)}</strong>
         </div>
         <div className="progress-label">
          <span>손절가 {formatPrice(row.minimum_selling_price)}</span>
          <b>목표 도달 {number(progress,0)}%</b>
          <span>목표가 {formatPrice(row.expected_selling_price)}</span>
         </div>
         <div className="progress"><i style={{width:`${visual}%`}}/></div>
         <div className="meta">
          <span><small>기준가</small>{formatPrice(row.setting_price)}</span>
          <span><small>갱신 단계</small>{row.renewal_cnt}단계</span>
          <span><small>최근 갱신</small>{display('pricing_reference_date',row.pricing_reference_date)}</span>
         </div>
         {market==='upbit'&&onAskAI&&(
          <div className="rec-card-action">
           <button className="btn-rec-ask-ai" onClick={()=>onAskAI(row.code)}>
            <span>✨ AI 분석 바로가기</span>
           </button>
          </div>
         )}
        </article>
       );
      })}
     </div>
     <Pager page={pagination.page} pages={pagination.pages} onChange={pagination.setPage}/>
    </>
   )}
  </>
 );
}
function DividendCards({rows}){const pagination=usePagination(rows,12);if(!rows?.length)return <Empty text="배당 정보 수집이 끝나면 이곳에 표시됩니다."/>;return <><div className="info-note"><b>배당수익률이란?</b><span>최근 공시 기준 주당 배당금을 현재 주가로 나눈 연 환산 비율입니다. 실제 지급액과 향후 배당을 보장하는 수치는 아닙니다.</span></div><p className="summary">배당수익률 상위 <b>{rows.length}</b>개 종목 · 네이버 금융 기준</p><div className="dividend-grid">{pagination.items.map(row=><article className="card dividend" key={row.code}><div><h3>{row.name}</h3><small>{row.code}</small></div><strong>{number(row.dividend_rate)}%</strong></article>)}</div><Pager page={pagination.page} pages={pagination.pages} onChange={pagination.setPage}/></>}

function SlideToConfirm({onConfirm,disabled,label="오른쪽으로 밀어서 매도"}) {
 const [dragPct,setDragPct]=useState(0);
 const [confirmed,setConfirmed]=useState(false);
 const [isDragging,setIsDragging]=useState(false);
 const trackRef=useRef(null);
 const activePointerId=useRef(null);

 useEffect(()=>{
  if(!disabled){
   setConfirmed(false);
   setDragPct(0);
   setIsDragging(false);
  }
 },[disabled]);

 function handlePointerDown(e){
  if(disabled||confirmed||!trackRef.current)return;
  const rect=trackRef.current.getBoundingClientRect();
  const touchX=e.clientX-rect.left;
  // Fail-safe: Drag must originate on or near the handle (left 64px)
  // Tapping anywhere else on the track does NOT trigger or jump!
  if(touchX>64)return;
  activePointerId.current=e.pointerId;
  try{e.currentTarget.setPointerCapture(e.pointerId)}catch(_){}
  setIsDragging(true);
 }

 function handlePointerMove(e){
  if(!isDragging||confirmed||disabled||!trackRef.current)return;
  if(activePointerId.current!==null&&e.pointerId!==activePointerId.current)return;
  const rect=trackRef.current.getBoundingClientRect();
  const maxDrag=Math.max(1,rect.width-54);
  const currentX=e.clientX-rect.left-4;
  const pct=Math.max(0,Math.min(100,(currentX/maxDrag)*100));
  setDragPct(pct);
  if(pct>=90&&!confirmed){
   setIsDragging(false);
   setConfirmed(true);
   setDragPct(100);
   activePointerId.current=null;
   if(typeof window!=='undefined'&&window.navigator?.vibrate){
    try{window.navigator.vibrate(50)}catch(_){}
   }
   onConfirm();
  }
 }

 function handlePointerUp(e){
  if(!isDragging)return;
  if(activePointerId.current!==null&&e.pointerId!==activePointerId.current)return;
  activePointerId.current=null;
  setIsDragging(false);
  if(!confirmed&&dragPct<90){
   setDragPct(0);
  }
 }

 const trackWidth=trackRef.current?trackRef.current.getBoundingClientRect().width:320;
 const maxOffset=Math.max(0,trackWidth-54);
 const handleOffset=(dragPct/100)*maxOffset;

 return (
  <div
   className={`slide-track ${confirmed?'confirmed':''} ${isDragging?'dragging':''}`}
   ref={trackRef}
   onPointerDown={handlePointerDown}
   onPointerMove={handlePointerMove}
   onPointerUp={handlePointerUp}
   onPointerCancel={handlePointerUp}
   role="slider"
   aria-valuemin={0}
   aria-valuemax={100}
   aria-valuenow={Math.round(dragPct)}
   aria-label="안전 매도 확인 슬라이더"
  >
   <div className="slide-fill" style={{width:`${Math.max(handleOffset+27,0)}px`}} />
   <span className="slide-label">
    {confirmed?'주문 전송 중…':(
     <span className="slide-label-content">
      <span>{label}</span>
      <span className="slide-chevrons">›››</span>
     </span>
    )}
   </span>
   <div
    className="slide-handle"
    style={{
     transform:`translateX(${handleOffset}px)`,
     transition:isDragging?'none':'transform 0.22s cubic-bezier(0.2,0.9,0.3,1)'
    }}
   >
    {confirmed?'✓':'→'}
   </div>
  </div>
 );
}

function Account({snapshot,reload,setError,user,onAskAI,onNavigate}) {
 const [access,setAccess]=useState(''),[secret,setSecret]=useState(''),[saving,setSaving]=useState(false),[showKeys,setShowKeys]=useState(false);
 const [sellTarget,setSellTarget]=useState(null),[selling,setSelling]=useState(false),[message,setMessage]=useState('');
 const [filter,setFilter]=useState('all');
 const [togglingAuto,setTogglingAuto]=useState(false);
 const [pullDist,setPullDist]=useState(0);
 const [countdown,setCountdown]=useState(snapshot?.safety?.next_decision_seconds??30);
 const touchStart=useRef(0);
 const saveLock=useRef(false),sellLock=useRef(false);

 useEffect(()=>{
  setCountdown(snapshot?.safety?.next_decision_seconds??30);
 },[snapshot?.safety?.next_decision_seconds]);

 useEffect(()=>{
  const timer=setInterval(()=>{
   setCountdown(prev=>(prev>1?prev-1:30));
  },1000);
  return()=>clearInterval(timer);
 },[]);

 const assets=snapshot?.assets||[];
 const incomplete=snapshot?.valuation_complete===false;
 const performance=snapshot?.performance||{};
 const safety=snapshot?.safety||{};
 const aiSummary=snapshot?.ai_summary||{};
 const notifications=snapshot?.notifications||[];
 const todayOrders=snapshot?.today_orders||[];
 const money=(value,digits=0)=>value==null?'시세 확인 불가':`₩ ${number(value,digits)}`;

 async function save(){
  if(saveLock.current)return;
  saveLock.current=true;setSaving(true);setError('');
  try{
   await api('/upbit/key',{method:'PUT',body:JSON.stringify({access_key:access.trim(),secret_key:secret.trim()})});
   setAccess('');setSecret('');setShowKeys(false);
   await reload();
  }catch(e){setError(e)}finally{saveLock.current=false;setSaving(false)}
 }

 async function sell(){
  if(!sellTarget||sellLock.current)return;
  sellLock.current=true;setSelling(true);setError('');setMessage('');
  try{
   const result=await api('/upbit/orders/market-sell',{
    method:'POST',
    body:JSON.stringify({
     market:`KRW-${sellTarget.currency}`,
     expected_available_quantity:String(sellTarget.balance),
     confirm:true,
     keep_auto:true
    })
   });
   setSellTarget(null);
   setMessage(`${result.market} 시장가 매도 주문을 접수했습니다. 자동매매는 유지되며 이 종목만 10분간 재매수하지 않습니다. 주문 내역에서 체결 상태를 확인하세요.`);
   await reload();
  }catch(e){setError(e)}finally{sellLock.current=false;setSelling(false)}
 }

 async function toggleAuto(){
  if(togglingAuto)return;
  setTogglingAuto(true);setError('');
  try{
   await api('/upbit/auto',{method:'PUT',body:JSON.stringify({auto_on:!snapshot?.auto_on})});
   await reload();
  }catch(e){setError(e)}finally{setTogglingAuto(false)}
 }

 function onTouchStart(e){
  if(window.scrollY<=2)touchStart.current=e.touches[0].clientY;
  else touchStart.current=0;
 }
 function onTouchMove(e){
  if(touchStart.current>0&&window.scrollY<=2){
   const diff=e.touches[0].clientY-touchStart.current;
   if(diff>0)setPullDist(Math.min(70,diff*0.45));
  }
 }
 function onTouchEnd(){
  if(pullDist>45){setPullDist(0);reload();}else{setPullDist(0);}
  touchStart.current=0;
 }

 const todayChange=performance.today_change;
 const todayChangeRate=performance.today_change_rate;
 const unrealized=performance.unrealized_profit;
 const unrealizedRate=performance.unrealized_rate;
 const autoOn=Boolean(snapshot?.auto_on);
 const keyRegistered=Boolean(snapshot?.key_registered);
 const safetyLevel=!keyRegistered?'warning':!autoOn?'neutral':!safety?.price_healthy?'delayed':'healthy';

 const coinAssets=assets.filter(a=>a.currency!=='KRW');
 const krwAsset=assets.find(a=>a.currency==='KRW');
 const visibleAssets=filter==='coins'?coinAssets:filter==='krw'?(krwAsset?[krwAsset]:[]):assets;

 return (
  <div className="dashboard-stack" onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
   {pullDist>0&&<div className="pull-refresh-indicator"><span>{pullDist>45?'손을 떼면 새로고침합니다':'아래로 당겨서 새로고침'}</span></div>}
   {message&&<div className="notice" role="status">{message}</div>}

   <section className="dashboard-hero-card">
    <div className="hero-main-row">
     <div className="hero-balance-section">
      <div className="hero-label">
       <span>{incomplete?'확인된 총 평가금액':'총 평가금액'}</span>
       <span className="hero-badge">포트폴리오</span>
      </div>
      <div className="hero-valuation">{formatKrw(snapshot?.total_valuation)}</div>
      {todayChange!=null?(
       <div className={`hero-pnl-pill ${todayChange>0?'up':todayChange<0?'down':'neutral'}`}>
        <span>오늘 변동</span>
        <strong>{todayChange>0?'+':''}{number(todayChange)}원</strong>
        <span>({todayChangeRate!=null&&todayChangeRate>0?'+':''}{number(todayChangeRate??0)}%)</span>
       </div>
      ):(
       <small style={{color:'#7b95ae'}}>당일 기준 자산 변동 집계 중</small>
      )}
     </div>
    </div>

    <div className="hero-submetrics">
     <div className="submetric-item">
      <small>미실현 손익</small>
      <strong style={{color:(unrealized??0)>=0?'#ff7e8e':'#72b2ff'}}>
       {unrealized!=null?`${unrealized>0?'+':''}${number(unrealized)}원`:'—'}
      </strong>
     </div>
     <div className="submetric-item">
      <small>평가 수익률</small>
      <strong style={{color:(unrealizedRate??0)>=0?'#ff7e8e':'#72b2ff'}}>
       {unrealizedRate!=null?signed(unrealizedRate):'—'}
      </strong>
     </div>
     <div className="submetric-item">
      <small>총 매수 원금</small>
      <strong>{formatKrw(performance.invested)}</strong>
     </div>
     <div className="submetric-item">
      <small>오늘 체결 건수</small>
      <strong>{snapshot?.today_executed_count||0}건</strong>
     </div>
    </div>
   </section>

   <section className="safety-bar-card">
    <div className="safety-bar-left">
     <div className={`safety-dot ${safetyLevel}`} />
     <div className="safety-statement">
      <h4>
       {!keyRegistered
        ?'Upbit API 키 미등록 상태'
        :!autoOn
        ?'자동매매가 일시 중지되어 있습니다'
        :!safety?.price_healthy
        ?'가격 갱신 지연으로 신규 매수가 제한될 수 있습니다'
        :'자동매매 정상 가동 중'}
      </h4>
      <span>
       {autoOn
        ?`다음 자동 판단 약 ${countdown}초 후 · 마지막 가격 확인 ${display('updated_at',safety?.price_updated_at)}`
        :'Upbit API 키로 안전하게 연결되어 있습니다. 언제든 자동매매를 켤 수 있습니다.'}
      </span>
     </div>
    </div>
    <div className="safety-bar-right">
     {keyRegistered&&(
      <button
       className={`btn-auto-toggle ${autoOn?'on':'off'}`}
       disabled={togglingAuto}
       onClick={toggleAuto}
      >
       <span className="toggle-dot" />
       <span>{togglingAuto?'변경 중…':autoOn?'자동매매 켜짐 (끄기)':'자동매매 꺼짐 (켜기)'}</span>
      </button>
     )}
    </div>
   </section>

   {notifications.length>0&&(
    <section className="dashboard-alerts-tray">
     {notifications.map(item=>(
      <div key={item.id} className={`dashboard-alert-pill ${item.level}`}>
       <div><b>{item.title}</b> — <span>{item.message}</span></div>
       {item.id==='ai-sell'&&onNavigate&&(
        <button onClick={()=>onNavigate('ai')}>AI 분석 바로가기</button>
       )}
       {item.id==='recent-error'&&onNavigate&&(
        <button onClick={()=>onNavigate('errors')}>오류 로그 확인</button>
       )}
      </div>
     ))}
    </section>
   )}

   <section className="dashboard-holdings">
    <div className="holdings-header">
     <h2>보유 자산 <span className="badge-count">{assets.length}</span></h2>
     <div className="holdings-filter-tabs">
      <button className={filter==='all'?'active':''} onClick={()=>setFilter('all')}>전체 ({assets.length})</button>
      <button className={filter==='coins'?'active':''} onClick={()=>setFilter('coins')}>코인 ({coinAssets.length})</button>
      {krwAsset&&(
       <button className={filter==='krw'?'active':''} onClick={()=>setFilter('krw')}>원화 잔고</button>
      )}
      <button className="quiet" onClick={()=>setShowKeys(!showKeys)}>
       {showKeys?'닫기':'API 키'}
      </button>
     </div>
    </div>

    {!visibleAssets.length?(
     <Empty text="표시할 보유 자산이 없습니다." />
    ):(
     <div className="holdings-grid">
      {visibleAssets.map(row=>{
       const available=Number(row.balance||0);
       const isKrw=row.currency==='KRW';
       const isSellAction=row.ai_action==='SELL';

       if(isKrw){
        return (
         <article className="holding-card krw-cash-card" key="KRW">
          <div className="holding-card-top">
           <div className="coin-identity">
            <div className="coin-badge krw-badge">₩</div>
            <div className="coin-names">
             <h3>원화 예수금 (KRW)</h3>
             <small>주문 가능 원화 잔고</small>
            </div>
           </div>
           <div className="coin-valuation-block">
            <span className="coin-valuation-amount">{formatKrw(row.balance)}</span>
            <small style={{color:'#7b95ae',fontSize:'11px'}}>보유액 100% 매수 가능</small>
           </div>
          </div>
         </article>
        );
       }

       return (
        <article
         className={`holding-card ${isSellAction?'has-sell-alert':''}`}
         key={row.currency}
        >
         <div className="holding-card-top">
          <div className="coin-identity">
           <div className="coin-badge">{row.currency}</div>
           <div className="coin-names">
            <h3>{row.currency}</h3>
            <small>보유 {formatQty(row.quantity)} · 매도 가능 {formatQty(row.balance)}</small>
           </div>
          </div>
          <div className="coin-valuation-block">
           <span className="coin-valuation-amount">{formatKrw(row.valuation)}</span>
           {row.profit_rate!=null&&(
            <span className={`coin-return-badge ${Number(row.profit_rate)>=0?'up':'down'}`}>
             {Number(row.profit_rate)>=0?'+':''}{number(row.profit_rate)}%
            </span>
           )}
          </div>
         </div>

         <div className="holding-prices-grid">
          <div><small>현재가</small><strong>{formatPrice(row.current_price)}</strong></div>
          <div><small>평균 매수가</small><strong>{formatPrice(row.avg_buy_price)}</strong></div>
          <div>
           <small>평가 손익</small>
           <strong style={{color:(row.valuation-row.purchase_amount)>=0?'#ff7e8e':'#72b2ff'}}>
            {row.valuation&&row.purchase_amount?`${(row.valuation-row.purchase_amount)>0?'+':''}${formatKrw(row.valuation-row.purchase_amount)}`:'—'}
           </strong>
          </div>
         </div>

         {row.target_price&&(
          <div className="targets-section">
           <div className="targets-header-line">
            <span className="stop-text">
             손절 {formatPrice(row.stop_loss_price)} ({row.distance_to_stop_pct!=null?`-${number(row.distance_to_stop_pct)}%`:'—'})
            </span>
            <span className="target-text">
             목표 {formatPrice(row.target_price)} ({row.distance_to_target_pct!=null?`+${number(row.distance_to_target_pct)}%`:'—'})
            </span>
           </div>
           <div className="targets-track">
            <div className="targets-fill" style={{width:`${Math.max(0,Math.min(100,row.target_progress||0))}%`}} />
           </div>
           <div className="targets-footer-line">
            <span>목표 도달 {number(row.target_progress||0,0)}%</span>
            {row.renewal_cnt!=null&&<span>추천 갱신 {row.renewal_cnt}단계</span>}
           </div>
          </div>
         )}

         {row.ai_action&&(
          <div className={`ai-insight-box ${String(row.ai_action).toLowerCase()}`}>
           <div className="ai-insight-header">
            <span className="ai-meta-text">AI 분석 판단</span>
            <span className={`ai-tag ${String(row.ai_action).toLowerCase()}`}>
             {row.ai_action==='SELL'?'매도 검토':row.ai_action==='HOLD'?'보유 권장':'관망'}
            </span>
           </div>
           {row.ai_reason&&<p className="ai-reason-text">{row.ai_reason}</p>}
           {row.ai_confidence&&<span className="ai-meta-text">근거 확신도 {row.ai_confidence}%</span>}
          </div>
         )}

         <div className="holding-safe-actions">
          <button className="btn-ai-ask" onClick={()=>onAskAI&&onAskAI(row.currency)}>
           <span>✨ AI에게 물어보기</span>
          </button>
          {user?.user_role==='MASTER'&&available>0&&(
           <button
            className="btn-safe-sell-open"
            onClick={()=>{setSellTarget(row);setMessage('');}}
            title="안전 매도 주문 창 열기"
           >
            <span>🛡️ 매도 검토</span>
           </button>
          )}
         </div>
        </article>
       );
      })}
     </div>
    )}
   </section>

   <section className="today-orders-card">
    <div className="today-orders-top">
     <h3>오늘 체결된 주문 ({todayOrders.length}건)</h3>
     {onNavigate&&(
      <button className="quiet compact" onClick={()=>onNavigate('orders')}>
       전체 내역 보기 →
      </button>
     )}
    </div>
    {todayOrders.length>0?(
     <div className="today-orders-table">
      {todayOrders.map(order=>(
       <div key={order.uuid} className="today-order-item">
        <div className="today-order-left">
         <span className={`order-badge-side ${order.side}`}>{display('side',order.side)}</span>
         <strong>{order.market}</strong>
         <small>{display('created_at',order.created_at)}</small>
        </div>
        <div className="today-order-right">
         <span>체결 {formatQty(order.executed_volume)}</span>
         <span>{order.price?`단가 ${formatPrice(order.price)}`:'시장가'}</span>
        </div>
       </div>
      ))}
     </div>
    ):(
     <p className="summary" style={{margin:0}}>오늘 체결 완료된 주문이 아직 없습니다.</p>
    )}
   </section>

   {sellTarget&&(
    <div className="safe-sell-overlay" onClick={()=>!selling&&setSellTarget(null)}>
     <div className="safe-sell-modal" onClick={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label="오작동 방지 안전 매도">
      <div className="safe-sell-header">
       <div className="safe-sell-title-wrap">
        <span className="safe-sell-shield-badge">🛡️ 오작동 방지 2단계 잠금</span>
        <h3>KRW-{sellTarget.currency} 시장가 매도</h3>
       </div>
       <button className="safe-sell-close-btn" disabled={selling} onClick={()=>setSellTarget(null)} aria-label="닫기">
        ✕
       </button>
      </div>

      <dl className="safe-sell-details">
       <div><dt>매도 종목</dt><dd>KRW-{sellTarget.currency}</dd></div>
       <div><dt>주문 수량</dt><dd>{formatQty(sellTarget.balance, sellTarget.currency)} (전량)</dd></div>
       <div><dt>현재가 환산액</dt><dd className="highlight-krw">{formatKrw(Number(sellTarget.balance||0)*Number(sellTarget.current_price||0))}</dd></div>
       {sellTarget.avg_buy_price&&(
        <div><dt>평균 매수가</dt><dd>{formatPrice(sellTarget.avg_buy_price)}</dd></div>
       )}
      </dl>

      <div className="safe-sell-warning-box">
       <b>실수 방지 안전 안내</b>
       <p>화면 실수 터치로 인한 오작동을 막기 위해 단일 탭으로는 주문이 실행되지 않습니다.</p>
       <p>아래 슬라이더의 핸들을 <strong>오른쪽 끝까지 밀어야</strong> 매도 주문이 접수되며, 체결 후 해당 종목은 10분간 자동 재매수에서 제외됩니다.</p>
      </div>

      <div className="slide-track-container">
       <SlideToConfirm
        key={sellTarget.currency}
        onConfirm={sell}
        disabled={selling}
        label={selling?"주문 처리 중…":"오른쪽으로 밀어서 매도 실행"}
       />
      </div>

      <button
       type="button"
       className="btn-safe-sell-cancel"
       disabled={selling}
       onClick={()=>setSellTarget(null)}
      >
       취소하고 돌아가기
      </button>
     </div>
    </div>
   )}

   {showKeys&&(
    <section className="card form narrow key-form">
     <h3>Upbit API 키 변경</h3>
     <p className="hint">키는 서버에만 안전하게 저장되며 화면에 다시 노출되지 않습니다.</p>
     <label>Access Key<input value={access} onChange={e=>setAccess(e.target.value)} autoComplete="off" /></label>
     <label>Secret Key<input type="password" value={secret} onChange={e=>setSecret(e.target.value)} autoComplete="new-password" /></label>
     <button className="primary" disabled={saving||!access.trim()||!secret.trim()} onClick={save}>
      {saving?'저장 중…':'API 키 저장'}
     </button>
    </section>
   )}
  </div>
 );
}
function Orders({rows}) {
 const pagination=usePagination(rows,10);
 if(!rows?.length)return <Empty text="자동매매 주문이 생성되면 이곳에 표시됩니다."/>;
 return (
  <>
   <p className="summary">최근 주문 <b>{rows.length}</b>건</p>
   <div className="order-list">
    {pagination.items.map(row=>{
     const marketBuy=row.side==='bid'&&row.ord_type==='price',cancel=orderStatus(row);
     return (
      <article className="card order" key={row.uuid}>
       <div className="order-head">
        <div>
         <span className={`order-side ${row.side}`}>{display('side',row.side)}</span>
         <h3>{row.market}</h3>
        </div>
        <span className={`order-state ${row.state}`}>{cancel?.label||display('state',row.state)}</span>
       </div>
       <div className="order-values">
        <span><small>주문 방식</small>{display('ord_type',row.ord_type)}</span>
        {row.price&&<span><small>{marketBuy?'요청 금액':'주문 가격'}</small>{formatPrice(row.price)}</span>}
        {!marketBuy&&row.volume&&<span><small>주문 수량</small>{formatQty(row.volume)}</span>}
        <span className="executed"><small>실제 체결 수량</small>{formatQty(row.executed_volume)}</span>
       </div>
       {cancel&&<p className="order-note">{cancel.note}</p>}
       <div className="order-foot">
        <time>{display('created_at',row.created_at)}</time>
        <details><summary>주문 번호 보기</summary><code>{row.uuid}</code></details>
       </div>
      </article>
     );
    })}
   </div>
   <Pager page={pagination.page} pages={pagination.pages} onChange={pagination.setPage}/>
  </>
 );
}
function ErrorLog({initial,setError}) {
 const [result,setResult]=useState(initial),[loading,setLoading]=useState(false),[source,setSource]=useState(''),[keyword,setKeyword]=useState('');
 const applied=useRef({source:'',keyword:''}),requests=useRef(createRequestGate()),pages=Math.max(1,Math.ceil(result.total/50));
 useEffect(()=>()=>requests.current.cancel(),[]);
 async function move(page,filters=applied.current){const request=requests.current.begin();setLoading(true);setError('');try{const query=new URLSearchParams({page:String(page),...filters});const next=await api(`/admin/errors?${query}`,{signal:request.signal});if(request.isCurrent()){applied.current=filters;setResult(next)}}catch(e){if(request.isCurrent())setError(e)}finally{if(request.isCurrent())setLoading(false)}}
 return <><form className="error-filters" onSubmit={e=>{e.preventDefault();move(0,{source,keyword:keyword.trim()})}}><label>오류 구분<select value={source} onChange={e=>setSource(e.target.value)}><option value="">전체</option><option value="UPBIT">Upbit</option><option value="STOCK">주식</option><option value="SYSTEM">시스템</option></select></label><label>작업·종류·내용 검색<input value={keyword} maxLength={100} onChange={e=>setKeyword(e.target.value)} placeholder="예: 429, FETCH_PRICE"/></label><button className="primary" type="submit">검색</button></form><p className="summary">조회된 오류 <b>{result.total}</b>건 · 페이지당 50건</p>{loading?<div className="loading-row" role="status"><div className="loader"/>불러오는 중입니다.</div>:<Table rows={result.items} columns={['created_at','source','operation','error_type','message']}/>}<Pager page={result.page} pages={pages} onChange={move}/></>
}
function Profile({user,onSaved,setError}){const [name,setName]=useState(user.user_name||''),[email,setEmail]=useState(user.user_email||''),[password,setPassword]=useState('');async function save(){setError('');try{await api('/profile',{method:'PUT',body:JSON.stringify({name,email:email||null,password:password||null})});setPassword('');await onSaved()}catch(e){setError(e)}}return <div className="card form narrow"><h3>프로필</h3><label>이름<input value={name} onChange={e=>setName(e.target.value)}/></label><label>이메일<input type="email" value={email} onChange={e=>setEmail(e.target.value)}/></label><label>새 비밀번호<input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="변경할 때만 입력"/></label><button className="primary" onClick={save}>변경사항 저장</button></div>}
function Settings({rows,onChange,onSave,pending}) {
 if(!rows?.length)return <Empty/>;
 const fields=[['expected_high_percentage','목표 상승률','기준 가격에서 목표 매도가까지의 비율','%',1,1000],['expected_low_percentage','허용 하락률','목표 상승률보다 작아야 합니다.','%',-99,999],['highest_price_reference_days','분석 기간','조회 가능한 범위: 3~200일','일',3,200]];
 return <div className="settings-grid">{rows.map((row,index)=><form className="card form" key={row.name} onSubmit={e=>{e.preventDefault();onSave(row)}}><div className="setting-title"><span className={`market ${row.name}`}>{row.name==='upbit'?'UPBIT':'STOCK'}</span><h3>{row.name==='upbit'?'Upbit 계산 기준':'주식 계산 기준'}</h3></div>{fields.map(([key,label,help,unit,min,max])=><label key={key}>{label}<small>{help}</small><div className="input-unit"><input type="number" value={row[key]} required step="1" min={min} max={key==='expected_low_percentage'?Math.min(max,Number(row.expected_high_percentage)-1):max} onChange={e=>onChange(index,key,e.target.value)}/><span>{unit}</span></div></label>)}<label className="check"><input type="checkbox" checked={row.volume_check} onChange={e=>onChange(index,'volume_check',e.target.checked)}/><span><b>거래량 조건 사용</b><small>추천 계산에 거래량 증가 여부를 반영합니다.</small></span></label><button className="primary" disabled={pending.includes(`settings-${row.name}`)}>{pending.includes(`settings-${row.name}`)?'저장 중…':'설정 저장'}</button></form>)}</div>
}

function App() {
 const [aiRefresh,setAiRefresh]=useState(0);
 const [aiInitialSymbol,setAiInitialSymbol]=useState('');
 const [user,setUser]=useState(null),[ready,setReady]=useState(false),[tab,setTab]=useState('account'),[data,setData]=useState(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[authMessage,setAuthMessage]=useState(''),[installPrompt,setInstallPrompt]=useState(null),[pending,setPending]=useState([]),[mobileMore,setMobileMore]=useState(false);
 const requests=useRef(createRequestGate()),authRequests=useRef(createRequestGate()),activeTab=useRef('account'),view=useRef(0),actions=useRef(new Set());
 const expireSession=useCallback(()=>{requests.current.cancel();view.current++;setData(null);setUser(null);setAuthMessage('로그인이 만료되었습니다. 다시 로그인해 주세요.')},[]);
 const handleError=useCallback(e=>{if(e?.status===401){expireSession();return}setError(typeof e==='string'?e:e?.message||'요청을 처리하지 못했습니다.')},[expireSession]);
 const loadUser=useCallback(async()=>{const request=authRequests.current.begin();try{const next=await api('/auth/me',{signal:request.signal});if(!request.isCurrent())return;if(!['ADMIN','MASTER'].includes(next.user_role)&&!['stock','upbit','dividends','orders','account','profile'].includes(activeTab.current)){activeTab.current='account';setTab('account')}setUser(next);setAuthMessage('')}catch(e){if(request.isCurrent()){setUser(null);if(e.status!==401)setAuthMessage(e.message)}}finally{if(request.isCurrent())setReady(true)}},[]);
 useEffect(()=>{loadUser();const handler=e=>{e.preventDefault();setInstallPrompt(e)};window.addEventListener('beforeinstallprompt',handler);return()=>{authRequests.current.cancel();window.removeEventListener('beforeinstallprompt',handler)}},[loadUser]);
 const load=useCallback(async()=>{
  if(activeTab.current!==tab)return;
  const request=requests.current.begin();view.current++;setLoading(true);setData(null);setError('');setNotice('');
  if(tab==='ai'){setAiRefresh(value=>value+1);setData({});setLoading(false);return;}
  let path=['stock','upbit'].includes(tab)?`/recommendations/${tab}`:`/admin/${tab}`;
  if(['dividends','orders'].includes(tab))path=`/${tab}`;
  if(tab==='account')path='/dashboard';if(tab==='profile')path='/auth/me';if(tab==='mail')path='/admin/mail-targets';
  try{const next=await api(path,{signal:request.signal});if(request.isCurrent())setData(next)}catch(e){if(request.isCurrent())handleError(e)}finally{if(request.isCurrent())setLoading(false)}
 },[tab,handleError]);
 useEffect(()=>{if(user)load();return()=>requests.current.cancel()},[user,load]);
 useEffect(()=>{if(!user||tab!=='upbit')return;let active=true;const timer=setInterval(async()=>{try{const next=await api('/recommendations/upbit?include_ownership=false');if(active&&activeTab.current==='upbit')setData(current=>next.map(row=>{const previous=Array.isArray(current)&&current.find(item=>item.code===row.code);return {...row,owned:previous?.owned,owned_quantity:previous?.owned_quantity}}))}catch(e){if(active&&e?.status===401)handleError(e)}},30000);return()=>{active=false;clearInterval(timer)}},[user,tab,handleError]);
 function selectTab(key){setMobileMore(false);if(key!=='ai')setAiInitialSymbol('');if(key===activeTab.current)return;requests.current.cancel();view.current++;activeTab.current=key;setData(null);setLoading(true);setError('');setNotice('');setTab(key)}
 function handleAskAI(currency){setAiInitialSymbol(`KRW-${currency}`);selectTab('ai');}
 async function mutate(key,action,{refresh=false,message=''}={}) {
  if(actions.current.has(key))return;
  const currentView=view.current;actions.current.add(key);setPending([...actions.current]);setError('');setNotice('');
  try{await action();if(view.current===currentView){if(refresh)await load();else if(message)setNotice(message)}}catch(e){if(view.current===currentView)handleError(e)}finally{actions.current.delete(key);setPending([...actions.current])}
 }
 async function logout(){await mutate('logout',async()=>{await api('/auth/logout',{method:'POST'});requests.current.cancel();authRequests.current.cancel();view.current++;setUser(null);setData(null);setAuthMessage('')})}
 function saveSetting(row){return mutate(`settings-${row.name}`,()=>api(`/admin/settings/${row.name}`,{method:'PUT',body:JSON.stringify({expected_high_percentage:Number(row.expected_high_percentage),expected_low_percentage:Number(row.expected_low_percentage),highest_price_reference_days:Number(row.highest_price_reference_days),volume_check:!!row.volume_check})}),{message:'설정을 저장했습니다. 다음 계산부터 적용됩니다.'})}
 if(!ready)return <main className="center"><div className="loader"/></main>;
 if(!user)return <Login onLogin={loadUser} message={authMessage}/>;
 const isAdmin=['ADMIN','MASTER'].includes(user.user_role),visible=tabs.filter(([key])=>isAdmin||['stock','upbit','dividends','orders','account','profile'].includes(key)),current=tabs.find(item=>item[0]===tab),currentView=view.current;
 const primaryKeys=['upbit','stock','account','ai'],mobilePrimary=visible.filter(([key])=>primaryKeys.includes(key)),mobileSecondary=visible.filter(([key])=>!primaryKeys.includes(key));
 const scopedError=e=>{if(view.current===currentView)handleError(e)};
 const statusLabel=loading?'조회 중':error?'조회 실패':data?'조회 완료':'대기 중';
 return <div className="layout"><aside><div className="brand"><img src="/icons/icon-192.png" alt=""/><div><h2>Trading</h2><p>{user.user_name} · {user.user_role}</p></div></div>{installPrompt&&<button className="install" onClick={async()=>{try{await installPrompt.prompt();setInstallPrompt(null)}catch(e){handleError(e)}}}>앱으로 설치</button>}<nav className="desktop-nav">{visible.map(([key,label,short])=><button className={tab===key?'active':''} onClick={()=>selectTab(key)} key={key}><span>{label}</span><small>{short}</small></button>)}</nav><nav className="mobile-nav" aria-label="주요 메뉴">{mobilePrimary.map(([key,label,short])=><button className={tab===key?'active':''} onClick={()=>selectTab(key)} key={key} title={label}><span>{label}</span><small>{short}</small></button>)}<button className={mobileMore||mobileSecondary.some(([key])=>key===tab)?'active':''} onClick={()=>setMobileMore(value=>!value)} aria-expanded={mobileMore}><span>나머지 메뉴</span><small>더보기</small></button></nav><button className="logout quiet" disabled={pending.includes('logout')} onClick={logout}>로그아웃</button></aside>{mobileMore&&<div className="mobile-more-backdrop" onClick={()=>setMobileMore(false)}><section className="mobile-more-sheet" role="dialog" aria-modal="true" aria-label="전체 메뉴" onClick={event=>event.stopPropagation()}><div className="section-head"><h2>전체 메뉴</h2><button className="quiet compact" onClick={()=>setMobileMore(false)}>닫기</button></div><div>{mobileSecondary.map(([key,label,short])=><button className={tab===key?'active':''} onClick={()=>selectTab(key)} key={key}><b>{short}</b><span>{label}</span></button>)}</div></section></div>}<main><header><div><small className="eyebrow">PERSONAL TRADING DESK</small><h1>{current?.[1]}</h1></div><div className="header-actions"><span className={`badge ${error?'failed':''}`} role="status">{statusLabel}</span><button className="refresh quiet" onClick={load} disabled={loading}>{error?'다시 시도':'새로고침'}</button></div></header>
 {error&&<div className="error" role="alert">{error}</div>}{notice&&<div className="notice" role="status">{notice}</div>}{loading&&<div className="loading-row" role="status"><div className="loader"/>데이터를 불러오는 중입니다.</div>}
 {data&&tab==='system'&&<section className="status-grid">{Object.entries(data).map(([key,value])=><article className="card status-card" key={key}><small>{labels[key]||key}</small><strong>{display(key,value)}</strong></article>)}</section>}
 {data&&['stock','upbit'].includes(tab)&&<>{tab==='upbit'&&data.some(row=>row.owned===null)&&<div className="info-note" role="status">보유 자산을 확인하지 못했습니다. 보유 표시 없이 추천 순서대로 표시합니다.</div>}<RecommendationCards key={tab} rows={data} market={tab} onAskAI={handleAskAI}/></>}
 {data&&tab==='dividends'&&<DividendCards rows={data}/>}
 {data&&tab==='orders'&&<Orders rows={data}/>}
 {data&&tab==='account'&&<Account snapshot={data} reload={load} setError={scopedError} user={user} onAskAI={handleAskAI} onNavigate={selectTab}/>}
 {data&&tab==='profile'&&<Profile user={data} onSaved={loadUser} setError={scopedError}/>}
 {data&&tab==='errors'&&<ErrorLog initial={data} setError={scopedError}/>}
 {tab==='ai'&&<AIAnalysis user={user} refreshToken={aiRefresh} setError={scopedError} onNavigate={setTab} initialSymbol={aiInitialSymbol}/>}
 {Array.isArray(data)&&tab==='autos'&&<div className="auto-grid">{data.map(row=><article className="card auto-card" key={row.user_login_id}><div><h3>{row.user_name}</h3><small>{row.user_login_id}</small></div><span className={`status-pill ${row.auto_on?'on':'off'}`}>{row.auto_on?'자동매매 사용 중':'자동매매 중지'}</span><p>{row.key_registered?'Upbit API 키가 등록되어 있습니다.':'API 키 등록 후 사용할 수 있습니다.'}</p><button className={row.auto_on?'danger':'primary'} disabled={!row.key_registered||pending.includes(`auto-${row.user_login_id}`)} onClick={()=>mutate(`auto-${row.user_login_id}`,()=>api(`/admin/autos/${encodeURIComponent(row.user_login_id)}`,{method:'PUT',body:JSON.stringify({auto_on:!row.auto_on})}),{refresh:true})}>{pending.includes(`auto-${row.user_login_id}`)?'변경 중…':row.auto_on?'자동매매 끄기':'자동매매 켜기'}</button></article>)}</div>}
 {Array.isArray(data)&&tab==='settings'&&<Settings rows={data} pending={pending} onChange={(index,key,value)=>setData(rows=>rows.map((row,i)=>i===index?{...row,[key]:value}:row))} onSave={saveSetting}/>}
 {data&&tab==='users'&&<Table rows={data}/>}
 {data&&tab==='mail'&&<><Table rows={data}/><button className="primary add-button" disabled={pending.includes('mail')} onClick={()=>{const email=prompt('추가할 이메일 주소');if(email?.trim())mutate('mail',()=>api('/admin/mail-targets',{method:'POST',body:JSON.stringify({email:email.trim()})}),{refresh:true})}}>메일 수신자 추가</button></>}
 </main></div>
}
createRoot(document.getElementById('root')).render(<App/>);
