# STOCK RADAR 개인용 클라우드 배포 안내 (Railway)

## 기능 범위
- 한국/미국 12개 종목 비공식 Yahoo Finance 가격 조회, RSS 뉴스 제목·링크, 규칙 기반 기술지표
- 실제 보유종목 수동 등록, 관심종목 등록, 모의거래 수동 입력, 일별 추천 스냅샷 및 5/20/60거래일 평가
- 오전 8시(Asia/Seoul) 서버 내 자동 갱신. 서버가 꺼져 있으면 실행되지 않으며 실행 중인 인스턴스 1개가 필요합니다.
- **실제 매매 자동화 없음. AI 언어모델 분석 없음. 관심종목 전체 자동 가격 수집 없음.**

## 배포 단계
1. GitHub 계정에서 **Private** 저장소 `stock-radar-private` 생성. 압축 해제한 `stock-radar-cloud` 폴더의 **내용물**을 업로드 (상위 폴더째 올리지 않기). `.env`/개인 DB/접근 키는 업로드 금지.
2. https://railway.com/ 가입 → New Project → Deploy from GitHub repo → 위 Private 저장소 선택. Dockerfile 자동 빌드.
3. 서비스 Variables에서 `RADAR_ACCESS_KEY`에 **무작위 32자 이상 비밀 문자열**을 설정. `ENABLE_MANUAL_REFRESH=false` 설정. 비밀 문자열은 채팅에 보내지 마세요.
4. 서비스에 Volume을 추가하고 **Mount Path를 `/app/data`** 로 지정. 반드시 실사용 보유종목 입력 전에 완료. 없으면 재배포 시 DB가 사라질 수 있습니다.
5. Settings → Networking → Generate Domain. HTTPS 주소로 접속해 개인 접근 키 입력.
6. Deploy Logs에서 오류가 없는지, 웹 화면에서 데이터 갱신 시각이 표시되는지 확인. 처음 가격 조회는 외부 API 제한으로 실패할 수 있습니다.
7. 아내분 노트북 Chrome/Edge에서 주소 열기 → 메뉴에서 바로가기 만들기. 노트북에는 Python 설치 불필요.

## 주의
- 공개 URL은 인터넷에서 접근 가능하므로 'Private GitHub'만으로 사이트가 비공개가 되지는 않습니다. 현재는 API 접근 키로 사용자 데이터 조회/수정을 제한하며, 화면 HTML은 공개됩니다.
- `RADAR_ACCESS_KEY`는 HTTPS에서만 입력하세요. 장기 운영 시 로그인 세션, 요청 횟수 제한, 접근 로그 모니터링 및 백업 기능을 추가하는 것이 좋습니다.
- DB는 SQLite `/app/data/portfolio.sqlite3`, 캐시는 `/app/data/snapshot.json`. 볼륨 스냅샷/백업 정책을 별도로 설정하세요.
- 비공식 금융 데이터는 누락/지연/제한 가능. 추천 성과 검증은 종가 스냅샷 기반으로, 실제 체결/장중 손절·익절 선도달을 검증하지 않습니다.
- 가격 데이터가 초기 조회에 실패해도 보유/관심종목 수동 입력 기능은 접근 키 설정 후 사용할 수 있습니다.
