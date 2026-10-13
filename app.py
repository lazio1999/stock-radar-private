import os, json, math, asyncio, logging, tempfile
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException, Header, Depends
from portfolio import router, record_snapshot, auth
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import yfinance as yf
import feedparser

ROOT=Path(__file__).parent
CACHE=ROOT/'data'/'snapshot.json'
KST=ZoneInfo('Asia/Seoul')
TICKERS={'KR':{'005930.KS':'삼성전자','000660.KS':'SK하이닉스','035420.KS':'NAVER','005380.KS':'현대차','068270.KS':'셀트리온','035720.KS':'카카오'},'US':{'AAPL':'Apple','MSFT':'Microsoft','NVDA':'NVIDIA','AMZN':'Amazon','GOOGL':'Alphabet','META':'Meta'}}
state={'generated_at':None,'items':[],'errors':[],'status':'not_loaded','data_source':'Yahoo Finance (비공식, 지연 가능)'}
lock=asyncio.Lock()

def safe(x):
    try:
        n=float(x)
        return round(n,4) if math.isfinite(n) else None
    except (TypeError,ValueError): return None

def compute(symbol,name,market):
    ticker=yf.Ticker(symbol)
    h=ticker.history(period='18mo',auto_adjust=True,actions=False)
    if h is None or len(h)<220: raise ValueError('가격 데이터 부족')
    h=h.dropna(subset=['Open','High','Low','Close','Volume'])
    c=h['Close']; v=h['Volume']; p=c.shift(1)
    tr=pd.concat([h['High']-h['Low'],(h['High']-p).abs(),(h['Low']-p).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14).mean().iloc[-1]
    price=float(c.iloc[-1]); ma50=float(c.rolling(50).mean().iloc[-1]); ma200=float(c.rolling(200).mean().iloc[-1]);
    high52=float(h['High'].tail(252).max()); volratio=float(v.iloc[-1]/v.tail(20).mean()) if v.tail(20).mean()>0 else 0
    return63=float(c.iloc[-1]/c.iloc[-64]-1) if len(c)>64 else None
    # 수급 데이터는 비공식 가격 API에서 제공되지 않음: 절대 추정하지 않음
    trend=price>ma200 and ma50>ma200
    breakout=price>float(h['High'].iloc[-21:-1].max()) and volratio>=1.5
    dist=2*float(atr); pct=dist/price
    signal=bool(trend and breakout and 0.05<=pct<=0.08)
    stop=price-dist; target1=price+2*dist; target2=price+3*dist
    currency='KRW' if market=='KR' else 'USD'
    # 분류는 기술적 관찰 유형이며 펀더멘털 가치평가/성장성 확정 아님
    styles=[]
    if trend: styles.append('모멘텀')
    if volratio>=1.5 and trend: styles.append('스윙')
    if not styles: styles=['관찰']
    return {'ticker':symbol,'name':name,'market':market,'currency':currency,'style':styles,'price':safe(price),'date':str(h.index[-1].date()),'ma50':safe(ma50),'ma200':safe(ma200),'volume_ratio':safe(volratio),'return_63d_pct':safe(return63*100) if return63 is not None else None,'high52':safe(high52),'atr14':safe(atr),'entry_reference':safe(price),'stop':safe(stop),'target1':safe(target1),'target2':safe(target2),'stop_pct':safe(pct*100),'signal':signal,'reason':'20일 고점 돌파·거래량 증가·장기 상승추세 충족' if signal else '기술적 관찰 대상: 매수 조건 전체 미충족','flow':'기관·외국인 수급 미연동 (확인 불가)','fundamentals':'가치·성장 펀더멘털 데이터 미연동','caution':'ATR 기준 시나리오. 다음 거래일 갭 및 체결 여부 확인 필요','news':news_for(name)}

def news_for(name):
    from urllib.parse import quote
    url='https://news.google.com/rss/search?q='+quote(name+' 주식 when:7d')+'&hl=ko&gl=KR&ceid=KR:ko'
    try:
        f=feedparser.parse(url)
        return [{'title':str(x.get('title',''))[:180],'url':str(x.get('link','')),'published':str(x.get('published',''))} for x in f.entries[:3] if str(x.get('link','')).startswith('https://')]
    except Exception: return []

def refresh_sync():
    items=[]; errors=[]
    for market, symbols in TICKERS.items():
        for symbol,name in symbols.items():
            try: items.append(compute(symbol,name,market))
            except Exception as exc:
                logging.warning('Failed %s: %s',symbol,exc)
                errors.append({'ticker':symbol,'message':str(exc)[:160]})
    if not items:
        return {'generated_at':datetime.now(KST).isoformat(),'items':[],'errors':errors,'status':'unavailable','data_source':'Yahoo Finance (비공식, 지연 가능)'}
    return {'generated_at':datetime.now(KST).isoformat(),'items':items,'errors':errors,'status':'partial' if errors else 'ok','data_source':'Yahoo Finance (비공식, 지연 가능)'}

async def refresh():
    global state
    async with lock:
        result=await asyncio.to_thread(refresh_sync)
        if result['items']:
            state=result
            record_snapshot(result["items"])
            CACHE.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=CACHE.parent,delete=False) as f:
                json.dump(state,f,ensure_ascii=False); temp=f.name
            os.replace(temp,CACHE)
        else:
            state={**state,'status':'stale' if state['items'] else 'unavailable','errors':result['errors']}
        return state

async def scheduler():
    last_day=None
    while True:
        now=datetime.now(KST)
        if now.hour>=8 and last_day!=now.date():
            try:
                await refresh()
                last_day=now.date()
            except Exception: logging.exception('Scheduled refresh failed')
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app):
    global state
    if CACHE.exists():
        try: state=json.loads(CACHE.read_text(encoding='utf-8'))
        except Exception: pass
    # 신규 서버 첫 실행 시에도 데이터가 보이도록 최초 조회를 백그라운드 실행
    initial=asyncio.create_task(refresh()) if not state.get('items') else None
    task=asyncio.create_task(scheduler())
    yield
    task.cancel()
    if initial and not initial.done(): initial.cancel()
    try: await task
    except asyncio.CancelledError: pass

app=FastAPI(title='Stock Radar',lifespan=lifespan)
app.include_router(router)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.get('/')
def home(): return FileResponse(ROOT/'static'/'index.html')
@app.get('/api/health')
def health(): return {'status':state['status'],'generated_at':state['generated_at'],'items':len(state['items'])}
@app.get('/api/radar')
def radar(x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    return state
@app.post('/api/refresh')
async def manual_refresh(x_radar_key: str|None=Header(None)):
    auth(x_radar_key)
    # 외부 배포 시 반드시 인증 적용. 기본값은 비활성화.
    if os.getenv('ENABLE_MANUAL_REFRESH')!='true': raise HTTPException(403,'관리자 갱신 기능 비활성화')
    return await refresh()
