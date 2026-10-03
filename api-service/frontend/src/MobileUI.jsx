import React, {useEffect, useRef, useState} from 'react';

export function useMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width:760px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width:760px)');
    const changed = () => setMobile(query.matches);
    query.addEventListener('change', changed);
    return () => query.removeEventListener('change', changed);
  }, []);
  return mobile;
}

export function Icon({name}) {
  const paths = {
    account:'M3 10 12 3l9 7M5 9v12h14V9M9 21v-7h6v7',
    upbit:'M4 17l5-6 4 3 7-10M15 4h5v5', stock:'M5 20V10m7 10V4m7 16v-7',
    ai:'M7 4h10l4 4v12H3V8l4-4M8 11h.01M16 11h.01M8 16h8M12 1v3',
    more:'M5 6h14M5 12h14M5 18h14', settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2',
    profile:'M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M4 21v-3a8 8 0 0 1 16 0v3',
    connections:'M10 14l4-4M9 8l2-2a5 5 0 0 1 7 7l-2 2M15 16l-2 2a5 5 0 0 1-7-7l2-2',
    refresh:'M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 14-2l1 7M19 17A8 8 0 0 1 5 19l-1-7',
    theme:'M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9',
    orders:'M6 3h12v18l-3-2-3 2-3-2-3 2V3M9 8h6M9 13h6',
    errors:'M12 3 2 21h20L12 3M12 9v5m0 3h.01',
    dividends:'M12 3v18M17 6H9a3 3 0 0 0 0 6h6a3 3 0 0 1 0 6H6',
    system:'M3 4h18v13H3V4M8 21h8M12 17v4',
    autos:'M5 8a8 8 0 0 1 14-2l2 2M21 3v5h-5M19 16a8 8 0 0 1-14 2l-2-2M3 21v-5h5',
    users:'M9 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8M2 21v-3a7 7 0 0 1 14 0v3M17 4a4 4 0 0 1 0 8M19 15a5 5 0 0 1 3 5',
    mail:'M3 5h18v14H3V5M3 5l9 8 9-8',
  };
  return <svg className="ui-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.settings}/></svg>;
}

export function Sheet({title, children, onClose, busy=false, className=''}) {
  const dialog = useRef(null), close = useRef(onClose), blocked = useRef(busy);
  close.current = onClose; blocked.current = busy;
  useEffect(() => {
    const previous = document.activeElement, oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current?.querySelector('button')?.focus();
    const keydown = event => {
      if (event.key === 'Escape' && !blocked.current) {event.preventDefault(); close.current();}
      if (event.key !== 'Tab') return;
      const targets = [...dialog.current.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]')].filter(el => el.getClientRects().length);
      const first = targets[0], last = targets.at(-1);
      if (!first) {event.preventDefault(); return;}
      if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
      else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
    };
    document.addEventListener('keydown', keydown);
    return () => {document.removeEventListener('keydown', keydown); document.body.style.overflow = oldOverflow; if(previous?.isConnected) previous.focus();};
  }, []);
  return <div className="ui-sheet-backdrop" onClick={() => !busy && onClose()}><section className={`ui-sheet ${className}`} role="dialog" aria-modal="true" aria-label={title} ref={dialog} onClick={event => event.stopPropagation()}><div className="ui-sheet-heading"><h2>{title}</h2><button className="quiet" disabled={busy} onClick={onClose}>닫기</button></div>{children}</section></div>;
}

export function ResponsivePanel({mobile, open=true, title, onClose, className='', children}) {
  if (!open) return null;
  return mobile ? <Sheet title={title} onClose={onClose} className={className}>{children}</Sheet> : <div className={className}>{children}</div>;
}
