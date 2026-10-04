"""Read-only operational history comparison. Run via api-service python stdin.
No market download, order, setting update, or error recording is performed.
"""
import json
import argparse
from collections import defaultdict
from datetime import datetime,timezone
from app.main import db,CALCULATION_SERVICE_URL
import httpx

def selected(prices,setting,amplitude,rounded):
    if len(prices)<3:return False
    last=1 if prices[0]['volume']==0 else 0
    recent=prices[last:last+3]
    if len(recent)<3 or recent[0]['close']==0:return False
    if setting['is_volume_check'] and prices[0]['volume']==max(row['volume'] for row in recent):return False
    if not recent[0]['high']>recent[1]['high']>recent[2]['high']:return False
    if not recent[0]['low']>recent[1]['low']>recent[2]['low']:return False
    threshold=recent[0]['high']*(1+float(setting['expected_low_percentage'])/100)
    if recent[0]['close']<(round(threshold) if rounded else threshold):return False
    if recent[0]['high']!=max(row['high'] for row in prices):return False
    if not amplitude:return True
    highs=[row['high'] for row in prices[:20]]
    if not highs or min(highs)==0:return False
    change=(max(highs)-min(highs))/min(highs)*100
    return float(setting['expected_high_percentage'])<=change<=float(setting['expected_high_percentage'])*3

def main(live_rule='rounded'):
    snapshots={};settings={}
    with db.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for market in ('stock','upbit'):
            cursor.execute('SELECT name,expected_high_percentage,expected_low_percentage,highest_price_reference_days,is_volume_check FROM deal_settings WHERE name=%s AND deleted_at IS NULL',(market,))
            settings[market]=cursor.fetchone()
            if not settings[market]:raise RuntimeError(f'Missing settings: {market}')
            cursor.execute(f'''SELECT DISTINCT ON (code,left(created_at,10)) code,name,close,high,low,volume,created_at
              FROM {market}_history WHERE deleted_at IS NULL ORDER BY code,left(created_at,10),created_at DESC,id DESC''')
            snapshots[market]=cursor.fetchall()
    report={'snapshot_at':datetime.now(timezone.utc).isoformat(),'settings':settings,'live_rule_verified':live_rule,'markets':{}}
    for market,rows in snapshots.items():
        grouped=defaultdict(list)
        for row in rows:grouped[row['code']].append(row)
        instruments=[]
        for code,history in grouped.items():
            history.sort(key=lambda row:row['created_at'],reverse=True)
            history=history[:int(settings[market]['highest_price_reference_days'])]
            prices=[{key:float(row[key]) for key in ('close','high','low','volume')} for row in history]
            if any(any(value<0 for value in price.values()) for price in prices):continue
            instruments.append({'code':code,'name':history[0]['name'],'prices':prices,'dates':[row['created_at'] for row in history]})
        if instruments:
            response=httpx.post(f'{CALCULATION_SERVICE_URL}/v1/recommendations/select',json={'instruments':[{key:item[key] for key in ('code','name','prices')} for item in instruments],
                'low_percentage':float(settings[market]['expected_low_percentage']),'high_percentage':float(settings[market]['expected_high_percentage']),
                'volume_check':settings[market]['is_volume_check'],'amplitude_check':market=='stock'},timeout=60)
            response.raise_for_status();actual=set(response.json()['selected_codes'])
            mirrored={item['code'] for item in instruments if selected(item['prices'],settings[market],market=='stock',live_rule=='rounded')}
            if actual!=mirrored:raise RuntimeError('Baseline mirror differs from running calculation service')
        for region in (('KR','US') if market=='stock' else ('UPBIT',)):
            scoped=[item for item in instruments if market=='upbit' or item['code'].startswith('US:')==(region=='US')]
            before={item['code'] for item in scoped if selected(item['prices'],settings[market],market=='stock',True)}
            after={item['code'] for item in scoped if selected(item['prices'],settings[market],market=='stock',False)}
            details=[]
            for item in scoped:
                if item['code'] not in before^after:continue
                recent=item['prices'][1 if item['prices'][0]['volume']==0 else 0]
                threshold=recent['high']*(1+float(settings[market]['expected_low_percentage'])/100)
                details.append({'code':item['code'],'name':item['name'],'close':recent['close'],'threshold':threshold,'rounded_threshold':round(threshold),
                    'change':'added' if item['code'] in after else 'removed','currency':'USD' if region=='US' else 'KRW'})
            dates=[date for item in scoped for date in item['dates']]
            historical={'checks':0,'rounded_selected':0,'unrounded_selected':0,'added':[],'removed':[]}
            for item in scoped:
                for index in range(len(item['prices'])-2):
                    window=item['prices'][index:]
                    if len(window)<(4 if window[0]['volume']==0 else 3):continue
                    was=selected(window,settings[market],market=='stock',True)
                    now=selected(window,settings[market],market=='stock',False)
                    historical['checks']+=1;historical['rounded_selected']+=int(was);historical['unrounded_selected']+=int(now)
                    if was!=now:
                        current=window[1 if window[0]['volume']==0 else 0];threshold=current['high']*(1+float(settings[market]['expected_low_percentage'])/100)
                        historical['added' if now else 'removed'].append({'code':item['code'],'date':item['dates'][index],
                            'close':current['close'],'threshold':threshold,'rounded_threshold':round(threshold)})
            report['markets'][region]={'instruments':len(scoped),'insufficient_history':sum(len(item['prices'])<(4 if item['prices'][0]['volume']==0 else 3) for item in scoped),
                'rounded_selected':len(before),'unrounded_selected':len(after),'added':sorted(after-before),'removed':sorted(before-after),'changes':details,
                'price_range':[min(item['prices'][0]['close'] for item in scoped),max(item['prices'][0]['close'] for item in scoped)] if scoped else None,
                'history_range':[min(dates),max(dates)] if dates else None,'historical':historical}
    print(json.dumps(report,ensure_ascii=False,default=str))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live-rule',choices=('rounded','unrounded'),default='rounded')
    main(parser.parse_args().live_rule)
