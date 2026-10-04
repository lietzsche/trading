import {afterEach,expect,it,vi} from 'vitest';
import {startVisiblePolling} from './visiblePolling';
afterEach(()=>vi.useRealTimers());
function documentMock(hidden=false){
  let listener;
  return {hidden,addEventListener:(_,fn)=>{listener=fn;},removeEventListener:()=>{listener=null;},
    change(value){this.hidden=value;listener?.();}};
}
it('pauses hidden tab and immediately resumes visible tab at 3-second intervals',async()=>{
  vi.useFakeTimers();const doc=documentMock(),poll=vi.fn(async()=>true);
  const stop=startVisiblePolling(poll,doc);await vi.advanceTimersByTimeAsync(3000);expect(poll).toHaveBeenCalledTimes(2);
  doc.change(true);await vi.advanceTimersByTimeAsync(9000);expect(poll).toHaveBeenCalledTimes(2);
  doc.change(false);await vi.advanceTimersByTimeAsync(0);expect(poll).toHaveBeenCalledTimes(3);
  stop();await vi.advanceTimersByTimeAsync(9000);expect(poll).toHaveBeenCalledTimes(3);
});
it('does not fetch initially hidden document',async()=>{
  const doc=documentMock(true),poll=vi.fn(async()=>false);const stop=startVisiblePolling(poll,doc);
  expect(poll).not.toHaveBeenCalled();doc.change(false);await Promise.resolve();expect(poll).toHaveBeenCalledTimes(1);stop();
});
it('does not schedule polling after cleanup during an in-flight request',async()=>{
  vi.useFakeTimers();let resolve;const poll=vi.fn(()=>new Promise(done=>{resolve=done;}));
  const stop=startVisiblePolling(poll,documentMock());stop();resolve(true);
  await vi.advanceTimersByTimeAsync(9000);expect(poll).toHaveBeenCalledTimes(1);
});
