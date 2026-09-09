import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

async function api(path, options={}) {
  const response = await fetch(`/api${path}`, {credentials:'same-origin', headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
  if (!response.ok) throw new Error((await response.json().catch(()=>({}))).detail || `요청 실패 (${response.status})`);
  return response.status === 204 ? null : response.json();
}

function Login({onLogin}) {
  const [loginId,setLoginId]=useState(''); const [password,setPassword]=useState(''); const [error,setError]=useState('');
  async function submit(e){e.preventDefault();setError('');try{await api('/auth/login',{method:'POST',body:JSON.stringify({login_id:loginId,password})});onLogin();}catch(e){setError(e.message)}}
  return <main className="login"><form className="card" onSubmit={submit}><h1>Trading Console</h1><p>신규 FastAPI · React 관리 화면</p><label>아이디<input autoFocus value={loginId} onChange={e=>setLoginId(e.target.value)}/></label><label>비밀번호<input type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label>{error&&<div className="error">{error}</div>}<button>로그인</button></form></main>
}

const tabs=[['system','시스템'],['upbit','Upbit 추천'],['stock','주식 추천'],['errors','오류'],['autos','자동매매'],['settings','계산 설정'],['users','사용자']];
function Table({rows}){if(!rows?.length)return <p className="empty">표시할 데이터가 없습니다.</p>;const keys=Object.keys(rows[0]);return <div className="table-wrap"><table><thead><tr>{keys.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={r.id??i}>{keys.map(k=><td key={k}>{String(r[k]??'')}</td>)}</tr>)}</tbody></table></div>}

function App(){
 const [user,setUser]=useState(null),[ready,setReady]=useState(false),[tab,setTab]=useState('system'),[data,setData]=useState(null),[error,setError]=useState('');
 const loadUser=()=>api('/auth/me').then(setUser).catch(()=>setUser(null)).finally(()=>setReady(true));
 useEffect(()=>{loadUser()},[]);
 useEffect(()=>{if(!user)return;setData(null);setError('');const path=['stock','upbit'].includes(tab)?`/recommendations/${tab}`:`/admin/${tab}`;api(path).then(setData).catch(e=>setError(e.message))},[user,tab]);
 async function toggleAuto(row){await api(`/admin/autos/${encodeURIComponent(row.user_login_id)}`,{method:'PUT',body:JSON.stringify({auto_on:!row.auto_on})});setData(await api('/admin/autos'))}
 async function saveSetting(row){const body={expected_high_percentage:+row.expected_high_percentage,expected_low_percentage:+row.expected_low_percentage,highest_price_reference_days:+row.highest_price_reference_days,volume_check:!!row.volume_check};await api(`/admin/settings/${row.name}`,{method:'PUT',body:JSON.stringify(body)});alert('저장했습니다.')}
 if(!ready)return <main className="center">불러오는 중…</main>; if(!user)return <Login onLogin={loadUser}/>;
 const isAdmin=['ADMIN','MASTER'].includes(user.user_role); const visible=tabs.filter(([key])=>isAdmin||['stock','upbit'].includes(key));
 return <div className="layout"><aside><h2>Trading</h2><p>{user.user_name} · {user.user_role}</p><nav>{visible.map(([key,label])=><button className={tab===key?'active':''} onClick={()=>setTab(key)} key={key}>{label}</button>)}</nav><button className="logout" onClick={async()=>{await api('/auth/logout',{method:'POST'});setUser(null)}}>로그아웃</button></aside><main><header><h1>{tabs.find(x=>x[0]===tab)?.[1]}</h1><span className="badge">병행 운영</span></header>{error&&<div className="error">{error}</div>}{!data&&!error&&<p>불러오는 중…</p>}{data&&tab==='system'&&<section className="grid">{Object.entries(data).map(([k,v])=><article className="card" key={k}><small>{k}</small><strong>{String(v)}</strong></article>)}</section>}{data&&['stock','upbit'].includes(tab)&&<Table rows={data}/>} {data&&tab==='errors'&&<Table rows={data.items}/>} {data&&tab==='autos'&&<div className="cards">{data.map(r=><article className="card" key={r.user_login_id}><b>{r.user_name}</b><span>{r.user_login_id}</span><button disabled={!r.key_registered} onClick={()=>toggleAuto(r)}>{r.auto_on?'자동매매 ON':'자동매매 OFF'}</button></article>)}</div>} {data&&tab==='settings'&&<div className="cards">{data.map((r,i)=><article className="card form" key={r.name}><h3>{r.name}</h3>{['expected_high_percentage','expected_low_percentage','highest_price_reference_days'].map(k=><label key={k}>{k}<input type="number" value={r[k]} onChange={e=>setData(data.map((x,j)=>j===i?{...x,[k]:e.target.value}:x))}/></label>)}<label><input type="checkbox" checked={r.volume_check} onChange={e=>setData(data.map((x,j)=>j===i?{...x,volume_check:e.target.checked}:x))}/> 거래량 확인</label><button onClick={()=>saveSetting(r)}>저장</button></article>)}</div>} {data&&tab==='users'&&<Table rows={data}/>}</main></div>
}
createRoot(document.getElementById('root')).render(<App/>);
