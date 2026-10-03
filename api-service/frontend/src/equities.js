export const equityRegion=row=>row.market_region || (String(row.code).startsWith('US:')?'US':'KR');
export const filterEquities=(rows,region)=>(rows||[]).filter(row=>region==='ALL'||equityRegion(row)===region);
export function dollarPrice(value){
  if(value==null||value===''||!Number.isFinite(Number(value)))return '—';
  return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(Number(value));
}
