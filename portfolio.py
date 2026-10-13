import os, sqlite3, json, secrets
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

DB=Path(__file__).parent/'data'/'portfolio.sqlite3'
router=APIRouter(prefix='/api')

def connection():
    DB.parent.mkdir(exist_ok=True,parents=True)
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS watchlist(symbol TEXT PRIMARY KEY, added TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS holdings(id INTEGER PRIMARY KEY AUTOINCREMENT,symbol TEXT NOT NULL,quantity REAL NOT NULL CHECK(quantity>0),cost REAL NOT NULL CHECK(cost>0),purchased TEXT NOT NULL,note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT,portfolio TEXT NOT NULL CHECK(portfolio IN ('mine','ai')),symbol TEXT NOT NULL,side TEXT NOT NULL CHECK(side IN ('buy','sell')),quantity REAL NOT NULL CHECK(quantity>0),price REAL NOT NULL CHECK(price>0),fee REAL NOT NULL DEFAULT 0 CHECK(fee>=0),executed TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS recommendations(id INTEGER PRIMARY KEY AUTOINCREMENT,day TEXT NOT NULL,symbol TEXT NOT NULL,style TEXT NOT NULL,reference_price REAL NOT NULL,stop REAL NOT NULL,target1 REAL NOT NULL,target2 REAL NOT NULL,signal INTEGER NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(day,symbol,style));
CREATE TABLE IF NOT EXISTS price_history(day TEXT NOT NULL,symbol TEXT NOT NULL,price REAL NOT NULL,PRIMARY KEY(day,symbol));''')
    return c

def now(): return datetime.now(timezone.utc).isoformat()

def auth(x_radar_key: str|None=Header(None)):
    key=os.getenv('RADAR_ACCESS_KEY','')
    if not key: raise HTTPException(503,'RADAR_ACCESS_KEY를 서버 환경변수로 설정해야 합니다')
    if not x_radar_key or not secrets.compare_digest(x_radar_key,key): raise HTTPException(401,'접근 키가 필요합니다')

def symbol_check(s):
    s=s.strip().upper()
    if not s or len(s)>20 or not all(x.isalnum() or x in '.-^' for x in s): raise HTTPException(400,'종목코드가 올바르지 않습니다')
    return s

class Watch(BaseModel): symbol:str
class Holding(BaseModel): symbol:str; quantity:float=Field(gt=0); cost:float=Field(gt=0); purchased:str; note:str=''
class Trade(BaseModel): portfolio:str; symbol:str; side:str; quantity:float=Field(gt=0); price:float=Field(gt=0); fee:float=Field(default=0,ge=0); executed:str; note:str=''

@router.get('/personal')
def personal(x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    with connection() as c:
        def rows(table): return [dict(x) for x in c.execute(f'SELECT * FROM {table} ORDER BY '+('symbol' if table=='watchlist' else 'id DESC' if table in ('holdings','trades','recommendations') else 'day DESC'))]
        return {'watchlist':rows('watchlist'),'holdings':rows('holdings'),'trades':rows('trades'),'recommendations':rows('recommendations')[:300]}

@router.post('/watchlist')
def add_watch(v:Watch,x_radar_key: str|None=Header(None)):
    auth(x_radar_key); s=symbol_check(v.symbol)
    with connection() as c: c.execute('INSERT OR IGNORE INTO watchlist VALUES(?,?)',(s,now()))
    return {'ok':True}
@router.delete('/watchlist/{symbol}')
def remove_watch(symbol:str,x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    with connection() as c: c.execute('DELETE FROM watchlist WHERE symbol=?',(symbol_check(symbol),))
    return {'ok':True}
@router.post('/holdings')
def add_holding(v:Holding,x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    with connection() as c: c.execute('INSERT INTO holdings(symbol,quantity,cost,purchased,note) VALUES(?,?,?,?,?)',(symbol_check(v.symbol),v.quantity,v.cost,v.purchased,v.note[:500]))
    return {'ok':True}
@router.delete('/holdings/{id}')
def delete_holding(id:int,x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    with connection() as c: c.execute('DELETE FROM holdings WHERE id=?',(id,))
    return {'ok':True}
@router.post('/trades')
def add_trade(v:Trade,x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    if v.portfolio not in ('mine','ai') or v.side not in ('buy','sell'): raise HTTPException(400,'유효하지 않은 매매')
    s=symbol_check(v.symbol)
    with connection() as c:
        if v.side=='sell':
            buy=c.execute("SELECT COALESCE(SUM(CASE WHEN side='buy' THEN quantity ELSE -quantity END),0) FROM trades WHERE portfolio=? AND symbol=?",(v.portfolio,s)).fetchone()[0]
            if v.quantity>buy+1e-8: raise HTTPException(400,'보유 수량보다 많이 매도할 수 없습니다')
        c.execute('INSERT INTO trades(portfolio,symbol,side,quantity,price,fee,executed,note) VALUES(?,?,?,?,?,?,?,?)',(v.portfolio,s,v.side,v.quantity,v.price,v.fee,v.executed,v.note[:500]))
    return {'ok':True}

def record_snapshot(items):
    if not items: return
    with connection() as c:
        for x in items:
            if not x.get('price') or not x.get('date'): continue
            s=x['ticker']; day=x['date']
            c.execute('INSERT OR IGNORE INTO price_history(day,symbol,price) VALUES(?,?,?)',(day,s,x['price']))
            if all(x.get(k) is not None for k in ('entry_reference','stop','target1','target2')):
                for style in x.get('style',[]):
                    c.execute('''INSERT OR IGNORE INTO recommendations(day,symbol,style,reference_price,stop,target1,target2,signal,reason,created) VALUES(?,?,?,?,?,?,?,?,?,?)''',(day,s,style,x['entry_reference'],x['stop'],x['target1'],x['target2'],int(x['signal']),x['reason'],now()))

@router.get('/evaluation')
def evaluation(x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    with connection() as c:
        recs=[dict(x) for x in c.execute('SELECT * FROM recommendations WHERE signal=1 ORDER BY id DESC LIMIT 500')]
        out=[]
        for r in recs:
            prices=[dict(x) for x in c.execute('SELECT day,price FROM price_history WHERE symbol=? AND day>? ORDER BY day',(r['symbol'],r['day']))]
            result={'symbol':r['symbol'],'day':r['day'],'style':r['style'],'reference_price':r['reference_price'],'observations':len(prices)}
            for n in (5,20,60):
                result[f'return_{n}d_pct']=round((prices[n-1]['price']/r['reference_price']-1)*100,2) if len(prices)>=n else None
            # 일별 종가로는 장중 목표/손절 선도달 여부를 확정할 수 없음
            out.append(result)
        return {'evaluations':out,'note':'이 평가는 일별 종가 스냅샷 기준입니다. 목표가/손절가 장중 선도달률은 OHLC 히스토리 기반 별도 검증 전까지 제공하지 않습니다.'}
