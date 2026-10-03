import React, {useEffect,useRef} from 'react';

export function Toast({message,onClose}) {
 const close=useRef(onClose);close.current=onClose;
 useEffect(()=>{if(!message)return;const timer=setTimeout(()=>close.current(),4000);return()=>clearTimeout(timer)},[message]);
 if(!message)return null;
 return <div className="notice success-toast" role="status"><span>{message}</span><button className="quiet" aria-label="알림 닫기" onClick={onClose}>닫기</button></div>;
}

export function ExpandableText({children}) {
 const [open,setOpen]=React.useState(false);
 const value=String(children??'—');
 return <div className="expandable-value"><span className={open?'':'clamped-value'}>{value}</span>{value.length>65&&<button className="quiet" aria-expanded={open} onClick={()=>setOpen(!open)}>{open?'접기':'펼치기'}</button>}</div>;
}
