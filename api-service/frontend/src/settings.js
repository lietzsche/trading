export function settingChangeText(key,value){
 if(value==null||value==='')return '—';
 if(key==='volume_check')return value?'사용':'미사용';
 if(key==='highest_price_reference_days')return `${Number(value)}일`;
 if(key==='expected_low_percentage')return `${Math.abs(Number(value))}%`;
 return `${Number(value)}%`;
}
