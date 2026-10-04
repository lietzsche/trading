import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {expect,it} from 'vitest';

for(const mode of ['navigate','cors'])for(const ok of [true,false]){
  it(`service worker ${mode} caches only successful response (ok=${ok})`,async()=>{
    const handlers={},writes=[];
    const response={ok,clone:()=>({copy:true})};
    runInNewContext(readFileSync(new URL('../public/sw.js',import.meta.url),'utf8'),{
      self:{addEventListener:(name,handler)=>{handlers[name]=handler;}},URL,
      location:{origin:'https://example.org'},fetch:async()=>response,
      caches:{match:async()=>undefined,open:async()=>({put:(...args)=>writes.push(args)})},
    });
    let pending;
    handlers.fetch({request:{method:'GET',url:'https://example.org/test',mode},respondWith:value=>{pending=value;}});
    expect(await pending).toBe(response);await Promise.resolve();expect(writes.length).toBe(ok?1:0);
  });
}
