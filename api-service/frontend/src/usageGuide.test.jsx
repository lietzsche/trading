import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it} from 'vitest';
import UsageGuide,{GUIDE_SECTIONS} from './UsageGuide';
it('renders six collapsible sections and documents actual safety limits',()=>{
 const html=renderToStaticMarkup(<UsageGuide/>);
 expect(GUIDE_SECTIONS).toHaveLength(6);expect(html.match(/<details /g)).toHaveLength(6);
 for(const text of ['3개 이상','10분','72시간','20회','14개','주문을 직접 실행하지 않습니다'])expect(html).toContain(text);
});
