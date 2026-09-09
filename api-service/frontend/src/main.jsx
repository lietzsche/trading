import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import './pwa.css';

if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));

async function api(path, options={}) {
  const response = await fetch(`/api${path}`, {credentials:'same-origin', headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
  if (!response.ok) throw new Error((await response.json().catch(()=>({}))).detail || `요청 실패 (${response.status})`);
  return response.status === 204 ? null : response.json();
}

function Login({onLogin}) {
  const [loginId,setLoginId]=useState(''); const [password,setPassword]=useState(''); const [error,setError]=useState(''); const [joining,setJoining]=useState(false); const [name,setName]=useState('');
  async function submit(e){e.preventDefault();setError('');try{if(joining){await api('/auth/join',{method:'POST',body:JSON.stringify({login_id:loginId,password,name})});setJoining(false);return}await api('/auth/login',{method:'POST',body:JSON.stringify({login_id:loginId,password})});onLogin();}catch(e){setError(e.message)}}
  return <main className="login"><form className="card" onSubmit={submit}><h1>Trading Console</h1><p>FastAPI · React 자동매매</p>{joining&&<label>이름<input value={name} onChange={e=>setName(e.target.value)}/></label>}<label>아이디<input autoFocus value={loginId} onChange={e=>setLoginId(e.target.value)}/></label><label>비밀번호<input type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label>{error&&<div className="error">{error}</div>}<button>{joining?'가입':'로그인'}</button><button type="button" onClick={()=>setJoining(!joining)}>{joining?'로그인으로':'회원가입'}</button></form></main>
}

const tabs=[['upbit','Upbit 추천'],['stock','주식 추천'],['dividends','배당주'],['orders','주문 내역'],['account','내 계좌'],['profile','내 정보'],['system','시스템'],['errors','오류'],['autos','자동매매'],['settings','계산 설정'],['users','사용자'],['mail','메일']];
function Table({rows}){if(!rows?.length)return <p className="empty">표시할 데이터가 없습니다.</p>;const keys=Object.keys(rows[0]);return <div className="table-wrap"><table><thead><tr>{keys.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={r.id??i}>{keys.map(k=><td key={k}>{String(r[k]??'')}</td>)}</tr>)}</tbody></table></div>}

function Account({rows,reload}){const [access,setAccess]=useState(''),[secret,setSecret]=useState('');async function save(){await api('/upbit/key',{method:'PUT',body:JSON.stringify({access_key:access,secret_key:secret})});setAccess('');setSecret('');reload()}return <><div className="card form"><h3>Upbit API 키</h3><label>Access key<input value={access} onChange={e=>setAccess(e.target.value)}/></label><label>Secret key<input type="password" value={secret} onChange={e=>setSecret(e.target.value)}/></label><button onClick={save}>안전하게 저장</button></div><h3>보유 자산</h3><Table rows={rows}/></>}

function Profile({user,onSaved}){const [name,setName]=useState(user.user_name||''),[email,setEmail]=useState(user.user_email||''),[password,setPassword]=useState('');async function save(){await api('/profile',{method:'PUT',body:JSON.stringify({name,email:email||null,phone:null,password:password||null})});setPassword('');onSaved()}return <div className="card form"><label>이름<input value={name} onChange={e=>setName(e.target.value)}/></label><label>이메일<input value={email} onChange={e=>setEmail(e.target.value)}/></label><label>새 비밀번호<input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="변경하지 않으면 비워두세요"/></label><button onClick={save}>저장</button></div>}

function App(){
 const [user,setUser]=useState(null),[ready,setReady]=useState(false),[tab,setTab]=useState('system'),[data,setData]=useState(null),[error,setError]=useState(''); const [installPrompt,setInstallPrompt]=useState(null);
 const loadUser=()=>api('/auth/me').then(setUser).catch(()=>setUser(null)).finally(()=>setReady(true));
 useEffect(()=>{loadUser();const handler=e=>{e.preventDefault();setInstallPrompt(e)};window.addEventListener('beforeinstallprompt',handler);return()=>window.removeEventListener('beforeinstallprompt',handler)},[]);
 const load=()=>{setData(null);setError('');let path=['stock','upbit'].includes(tab)?`/recommendations/${tab}`:`/admin/${tab}`;if(['dividends','orders'].includes(tab))path=`/${tab}`;if(tab==='account')path='/upbit/accounts';if(tab==='profile')path='/auth/me';if(tab==='mail')path='/admin/mail-targets';api(path).then(setData).catch(e=>setError(e.message))};
 const selectTab=key=>{setData(null);setError('');setTab(key)};
 useEffect(()=>{if(user)load()},[user,tab]);
 async function toggleAuto(row){await api(`/admin/autos/${encodeURIComponent(row.user_login_id)}`,{method:'PUT',body:JSON.stringify({auto_on:!row.auto_on})});setData(await api('/admin/autos'))}
 async function saveSetting(row){const body={expected_high_percentage:+row.expected_high_percentage,expected_low_percentage:+row.expected_low_percentage,highest_price_reference_days:+row.highest_price_reference_days,volume_check:!!row.volume_check};await api(`/admin/settings/${row.name}`,{method:'PUT',body:JSON.stringify(body)});alert('저장했습니다.')}
 if(!ready)return <main className="center">불러오는 중…</main>; if(!user)return <Login onLogin={loadUser}/>;
 const isAdmin=['ADMIN','MASTER'].includes(user.user_role); const visible=tabs.filter(([key])=>isAdmin||['stock','upbit','dividends','orders','account','profile'].includes(key));
 return <div className="layout"><aside><div className="brand"><img src="/icons/icon-192.png" alt=""/><div><h2>Trading</h2><p>{user.user_name} · {user.user_role}</p></div></div>{installPrompt&&<button className="install" onClick={async()=>{await installPrompt.prompt();setInstallPrompt(null)}}>앱으로 설치</button>}<nav>{visible.map(([key,label])=><button className={tab===key?'active':''} onClick={()=>selectTab(key)} key={key}>{label}</button>)}</nav><button className="logout" onClick={async()=>{await api('/auth/logout',{method:'POST'});setUser(null)}}>로그아웃</button></aside><main><header><div><small className="eyebrow">PERSONAL TRADING DESK</small><h1>{tabs.find(x=>x[0]===tab)?.[1]}</h1></div><span className="badge"><i/> Python 운영</span></header>{error&&<div className="error">{error}</div>}{!data&&!error&&<p>불러오는 중…</p>}{data&&tab==='system'&&<section className="grid">{Object.entries(data).map(([k,v])=><article className="card" key={k}><small>{k}</small><strong>{String(v)}</strong></article>)}</section>}{data&&['stock','upbit','dividends','orders'].includes(tab)&&<Table rows={data}/>} {data&&tab==='account'&&<Account rows={data} reload={load}/>} {data&&tab==='profile'&&<Profile user={data} onSaved={loadUser}/>} {data&&tab==='errors'&&<Table rows={data.items}/>} {Array.isArray(data)&&tab==='autos'&&<div className="cards">{data.map(r=><article className="card" key={r.user_login_id}><b>{r.user_name}</b><span>{r.user_login_id}</span><button disabled={!r.key_registered} onClick={()=>toggleAuto(r)}>{r.auto_on?'자동매매 ON':'자동매매 OFF'}</button></article>)}</div>} {Array.isArray(data)&&tab==='settings'&&<div className="cards">{data.map((r,i)=><article className="card form" key={r.name}><h3>{r.name}</h3>{['expected_high_percentage','expected_low_percentage','highest_price_reference_days'].map(k=><label key={k}>{k}<input type="number" value={r[k]} onChange={e=>setData(data.map((x,j)=>j===i?{...x,[k]:e.target.value}:x))}/></label>)}<label><input type="checkbox" checked={r.volume_check} onChange={e=>setData(data.map((x,j)=>j===i?{...x,volume_check:e.target.checked}:x))}/> 거래량 확인</label><button onClick={()=>saveSetting(r)}>저장</button></article>)}</div>} {data&&tab==='users'&&<Table rows={data}/>} {data&&tab==='mail'&&<><Table rows={data}/><button onClick={async()=>{const email=prompt('추가할 이메일');if(email){await api('/admin/mail-targets',{method:'POST',body:JSON.stringify({email})});load()}}}>수신자 추가</button></>}</main></div>
}
createRoot(document.getElementById('root')).render(<App/>);
