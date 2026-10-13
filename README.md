# STOCK RADAR LIVE BETA

기존 STOCK RADAR 데모를 바탕으로 만든 **실제 가격/거래량 조회 + 매일 오전 8시 자동 갱신 + 반응형 웹** MVP입니다.

## 로컬 실행

Python 3.11+ 권장:

```bash
cd stock-radar-live
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

브라우저에서 http://127.0.0.1:8000 접속. 서버 시작 후 KST 오전 8시 이후 최초 1회 수집합니다. 즉시 수집이 필요하면 개발환경에서만 `ENABLE_MANUAL_REFRESH=true` 설정 후 `POST /api/refresh` 호출하세요. Windows PowerShell 예: `$env:ENABLE_MANUAL_REFRESH="true"; uvicorn app:app --port 8000`, 다른 터미널에서 `Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/refresh`.

## Docker

```bash
docker build -t stock-radar .
docker run -d --name stock-radar -p 8000:8000 -v stockradar_data:/app/data --restart unless-stopped stock-radar
```

운영 서버에 올리고 HTTPS 도메인을 연결하면 모바일 브라우저에서 접근 가능합니다. Docker 컨테이너는 24시간 실행되어야 08:00 스케줄이 동작합니다. 서버가 중단되었다가 오전 8시 이후 재시작하면 당일 갱신을 시도합니다. 복수 인스턴스 운영 시 외부 스케줄러와 공유 DB를 사용하세요.

## 데이터와 한계

- Yahoo Finance 비공식 `yfinance`: 실시간·정확도·서비스 지속성·재배포 라이선스가 보장되지 않습니다. 유료 서비스 또는 외부 공개 시 정식 라이선스 데이터 공급자로 교체하세요.
- 뉴스: Google News RSS 제목/링크. 제목을 AI가 검증하거나 호재/악재로 판정하지 않습니다.
- **기관/외국인 수급, 분기 실적, 저평가 점수, 미국 13F는 미연동**입니다. 허위 수급·뉴스를 생성하지 않습니다.
- 한국/미국 각 6개 사전 지정 종목만 스캔합니다. 전체 시장 스크리너가 아닙니다.
- 신호는 `종가 > 200일선`, `50일선 > 200일선`, `직전 20일 고가 돌파`, `거래량 1.5배`, `2*ATR 손절폭 5~8%` 조건입니다. 아직 상대강도/실적/지수 필터 미연동입니다.
- 표시한 목표가는 ATR 기반 시나리오이며 예측가격이 아닙니다. 국내 주식 매수 수량은 5만원 계획손실/종목 200만원 한도로 계산합니다. 미국은 실시간 환율 부재로 수량 미계산.
- 시장 데이터는 휴장·타임존·공급자 장애에 따라 지연될 수 있습니다. 각 종목 가격 기준일과 스냅샷 생성시각을 따로 표시합니다.
- 공개 운영 전 관리자 인증, 레이트리밋, HTTPS, 접근제어, 장애 알림, DB 백업, 데이터 공급자 계약, 규제/광고 검토가 필요합니다.
- 이 MVP는 자동주문 기능이 없습니다. 종목 추천 성과가 검증된 것도 아닙니다.

## 다음 구현 우선순위

1. 공식 시세/기관·외국인 수급/재무/공시 데이터 연동 및 제공 라이선스 확인
2. KOSPI/KOSDAQ/S&P500 전체 유니버스, 지수 상대강도, 상장폐지 종목 포함 백테스트
3. 뉴스 원문·공시 기반 근거 추출, 출처/시각 표시, AI 해석과 사실 분리
4. 매매일지/포트폴리오 SQLite 또는 PostgreSQL, 사용자 로그인
5. 주문 없는 알림과 운영 모니터링, 정식 호스팅·도메인

## 2.0 개인 포트폴리오·모의거래·AI 검증

- `portfolio.py`: SQLite에 관심종목, 실제 보유내역(수동 입력), 가상 매매내역, 추천 신호 및 종가 스냅샷을 보존합니다.
- 서버 실행 전에 반드시 `RADAR_ACCESS_KEY` 환경변수에 길고 무작위인 비밀키를 설정하세요. 웹페이지에서 접속 시 입력합니다. 공용 PC 사용 금지. HTTPS 역방향 프록시 없이는 인터넷에 공개하지 마세요.
- `GET /api/personal`, `POST/DELETE /api/watchlist`, `POST/DELETE /api/holdings`, `POST /api/trades`, `GET /api/evaluation` 엔드포인트가 추가되었습니다.
- 현재 스캐너는 기존 12종목만 수집합니다. 관심종목에 추가한 다른 종목의 시세를 자동 수집하지는 않습니다.
- AI 추천 검증은 신규 스냅샷 수집일부터 시작합니다. 과거 추천 이력을 사후 생성하지 않습니다. 5·20·60 **관측 종가** 기반 수익률이며 장중 손절·익절 선도달 검증은 미구현입니다.
- 모의매매는 사용자가 체결가격을 수동 입력하는 기록장입니다. 자동 가상 체결이나 자동 포트폴리오 주문은 아직 구현하지 않았습니다.
- 미국/한국 종목의 손익은 통화별로 따로 표기하며 환산 합산하지 않습니다. 실제 평가손익은 종목 데이터가 있을 때만 표시됩니다.
- Yahoo Finance 비공식 데이터는 누락·지연·이용약관 변경 가능성이 있습니다. 실전 매매 결정에 단독 사용하지 마세요.
- 단일 프로세스로 실행하세요. 다중 worker는 별도 스케줄러 분리 전까지 중복 실행될 수 있습니다.

### 로컬 실행 예시
```bash
cd stock-radar-live
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export RADAR_ACCESS_KEY='CHANGE_ME_TO_A_RANDOM_LONG_SECRET'  # Windows PowerShell: $env:RADAR_ACCESS_KEY='...'
uvicorn app:app --host 127.0.0.1 --port 8000
```
브라우저에서 http://127.0.0.1:8000 접속 후 접근 키를 입력하세요. 처음 실행 시 서버가 오전 8시 이후라면 당일 데이터 갱신을 시도하며, 그렇지 않으면 첫 갱신까지 대기합니다. 외부 호스팅·도메인·HTTPS·실제 운영 확인은 아직 완료되지 않았습니다.
