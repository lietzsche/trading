import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it} from 'vitest';
import UsageGuide,{GUIDE_SECTIONS} from './UsageGuide';
it('documents the fixed MA40 strategy and order safety behavior',()=>{
 const html=renderToStaticMarkup(<UsageGuide/>);
 expect(GUIDE_SECTIONS).toHaveLength(6);expect(html.match(/<details/g)).toHaveLength(6);
 for(const text of ['완료 일봉 40개','다음 날 시가','5분','30초','재전송하지 않고','출금 권한은 부여하지 마세요'])expect(html).toContain(text);
});
