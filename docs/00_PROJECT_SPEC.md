# 00_PROJECT_SPEC.md

# Personal Trading OS MVP — Project Specification

**문서 버전:** v1.0  
**작성 기준일:** 2026-05-12  
**대상 사용자:** 개인 미국 주식 트레이더  
**개발 환경:** Windows  
**Python 버전:** 3.12  
**프로젝트 경로:** `C:\trading\personal_trading_os`  
**실행 방식:** `.venv\Scripts\python.exe` 직접 호출  
**스케줄러:** Windows Task Scheduler  
**전송 채널:** Telegram  
**AI 활용:** GPT Pro / Claude Max는 코딩 보조, 코드 리뷰, 프롬프트 생성, 수동 분석 보조에 사용  
**LLM API 사용 여부:** ChatGPT/OpenAI API, Claude API는 MVP에서 사용하지 않음  
**자동매매 여부:** 없음  
**TradingView scraping 여부:** 없음  

---

## 1. 프로젝트 목적

`Personal Trading OS MVP`는 미국 주식 개인 트레이더가 매일 장전/장마감에 사용할 수 있는 **트레이딩 운영 보조 시스템**이다.

이 프로그램의 목적은 뉴스 앱, 자동매매 봇, LLM 자동 리포트 생성기가 되는 것이 아니다. 핵심 목적은 다음과 같다.

1. 매일 시장 상태를 정량적으로 정리한다.
2. 관심종목을 A/B/C/D 등급으로 자동 분류한다.
3. 오늘 볼 종목과 피해야 할 종목을 줄여준다.
4. 주요 어닝/경제 이벤트 리스크를 자동으로 표시한다.
5. 매매원칙 위반 가능성을 사전에 경고한다.
6. GPT Pro와 Claude Max에 넣을 수 있는 분석용 패킷을 생성한다.
7. Telegram으로 매일 정리된 결과물을 전송한다.

이 프로그램은 최종 매수/매도 결정을 하지 않는다.  
최종 판단은 사용자가 SAVE, TradingView, 차트, 뉴스 맥락, 포지션 상황을 직접 확인한 뒤 내린다.

---

## 2. MVP 범위

### 2.1 포함 기능

MVP에 포함할 기능은 다음과 같다.

| 기능 | 처리 방식 | 설명 |
|---|---|---|
| 가격 데이터 수집 | 자동 | `yfinance` 기반으로 MVP 시작 |
| 기술 지표 계산 | 자동 | 20DMA, 50DMA, 200DMA, 거래량, 상대강도 등 |
| 시장 모드 판정 | 자동 | Risk-On / Mild Risk-On / Neutral / Caution / Defensive |
| 관심종목 랭킹 | 자동 | A/B/C/D 등급 분류 |
| 셋업 후보 분류 | 자동 | Breakout / Pullback / Avoid |
| 어닝 캘린더 수집 | 자동 | Alpha Vantage `EARNINGS_CALENDAR` |
| 경제 이벤트 수집 | 자동 | FMP Economic Calendar, BLS Calendar, Fed FOMC Calendar |
| 이벤트 리스크 반영 | 자동 | 어닝 7일 이내, 고영향 매크로 이벤트 반영 |
| 수동 뉴스 메모 반영 | 반자동 | SAVE/TradingView에서 확인한 뉴스를 `manual_news_notes.md`에 입력 |
| 리스크 경고 생성 | 자동 | VIX, 이벤트, 시장 모드, D급 종목 등 |
| 금지 행동 출력 | 자동 | 장초반 추격 금지, D급 물타기 금지 등 |
| Daily Packet 생성 | 자동 | `daily_packet.md`, `daily_packet.json` |
| GPT/Claude 프롬프트 생성 | 자동 | `prompt_for_gpt.txt`, `prompt_for_claude.txt` |
| Telegram 전송 | 자동 | 요약 메시지 + 파일 첨부 |
| Windows 자동 실행 | 자동 | Task Scheduler 사용 |

### 2.2 MVP 최종 출력물

MVP는 매 실행마다 다음 파일을 생성해야 한다.

```text
output\daily_packet.md
output\daily_packet.json
output\prompt_for_gpt.txt
output\prompt_for_claude.txt
output\telegram_summary.txt
output\events_auto.json
output\events_merged.json
```

---

## 3. 제외 범위

MVP에서 제외하는 항목은 다음과 같다.

1. 자동매매
2. 주문 API 연동
3. 브로커 API 연동
4. TradingView 웹페이지 scraping
5. TradingView 로그인 자동화
6. TradingView 비공식 API 또는 내부 WebSocket 사용
7. ChatGPT/OpenAI API를 통한 자동 리포트 생성
8. Claude API를 통한 자동 리포트 생성
9. 뉴스 자동 수집 및 자동 뉴스 요약
10. 옵션 데이터 분석
11. 고급 백테스트
12. 포트폴리오 손익 자동 계산
13. 실시간 장중 틱/분봉 기반 복잡한 알림
14. 자동 종목 추천 또는 매수/매도 추천

뉴스는 MVP에서 자동 수집하지 않는다.  
사용자는 SAVE, TradingView 개별 티커 뉴스, 직접 확인한 뉴스 소스를 통해 중요한 뉴스를 수동 확인하고, 필요할 경우 `data\manual_news_notes.md`에 입력한다.

---

## 4. 전체 데이터 흐름

### 4.1 자동 데이터 흐름

```text
Windows Task Scheduler
  ↓
run_post_close.bat
  ↓
.venv\Scripts\python.exe src\main.py --session post_close
  ↓
config 로드
  ↓
가격 데이터 수집
  ↓
기술 지표 계산
  ↓
어닝/경제 이벤트 자동 수집
  ↓
수동 이벤트/뉴스 메모 병합
  ↓
시장 모드 판정
  ↓
관심종목 A/B/C/D 랭킹
  ↓
셋업 후보 분류
  ↓
리스크 엔진 실행
  ↓
Daily Packet 생성
  ↓
GPT/Claude 프롬프트 생성
  ↓
Telegram 전송
```

### 4.2 사용자 수동 흐름

```text
Telegram 수신
  ↓
Daily Packet 확인
  ↓
SAVE / TradingView에서 중요 뉴스 수동 확인
  ↓
필요 시 manual_news_notes.md 업데이트
  ↓
prompt_for_gpt.txt를 ChatGPT Pro에 입력
  ↓
ChatGPT가 트레이딩 플랜 생성
  ↓
prompt_for_claude.txt를 Claude Max에 입력
  ↓
Claude가 리스크 리뷰 수행
  ↓
사용자가 최종 판단
```

---

## 5. Windows 개발 환경

### 5.1 기준 환경

```text
OS: Windows 10 또는 Windows 11
Python: 3.12
Shell: PowerShell 또는 CMD
Editor: VS Code 권장
Scheduler: Windows Task Scheduler
Project Path: C:\trading\personal_trading_os
```

### 5.2 Python 가상환경

가상환경은 프로젝트 루트에 `.venv`로 생성한다.

```powershell
cd C:\trading\personal_trading_os
py -3.12 -m venv .venv
```

패키지 설치는 항상 `.venv\Scripts\python.exe`를 직접 호출한다.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

자동 실행에서는 `activate`를 사용하지 않는다.

### 5.3 requirements.txt

```txt
pandas
numpy
yfinance
pyyaml
python-dotenv
requests
python-dateutil
pytz
beautifulsoup4
lxml
rich
pytest
```

### 5.4 Windows 경로 원칙

권장 경로:

```text
C:\trading\personal_trading_os
```

피해야 할 경로:

```text
C:\Users\사용자명\바탕 화면\미국 주식 프로그램
C:\Users\사용자명\OneDrive\문서\트레이딩 프로그램
```

경로에 한글, 공백, OneDrive 동기화 폴더가 들어가면 Task Scheduler 실행이나 로그 저장 중 문제가 생길 수 있으므로 피한다.

---

## 6. 파일/폴더 구조

최종 프로젝트 구조는 다음과 같다.

```text
C:\trading\personal_trading_os\
  config\
    watchlist.yaml
    rules.yaml
    setups.yaml
    settings.yaml
    events_manual.yaml

  data\
    manual_news_notes.md
    tradingview_screener.csv

  output\
    daily_packet.md
    daily_packet.json
    events_auto.json
    events_merged.json
    prompt_for_gpt.txt
    prompt_for_claude.txt
    telegram_summary.txt

  cache\
    prices_cache.json
    earnings_cache.json
    economic_events_cache.json

  logs\
    post_close.log
    pre_market.log

  src\
    main.py
    config_loader.py
    fetch_prices.py
    indicators.py
    market_regime.py
    watchlist_ranker.py
    setup_matcher.py
    event_sources.py
    event_calendar.py
    risk_engine.py
    packet_builder.py
    prompt_builder.py
    telegram_sender.py

  tests\
    test_market_regime.py
    test_watchlist_ranker.py
    test_event_calendar.py

  docs\
    00_PROJECT_SPEC.md
    01_RUNBOOK_WINDOWS.md
    02_ARCHITECTURE.md
    03_PROMPT_LIBRARY.md
    04_RULES_AND_SCORING.md
    05_DATA_SOURCES.md
    06_CODE_REVIEW_CHECKLIST.md
    07_CHANGELOG.md

  run_post_close.bat
  run_pre_market.bat
  .env
  .env.example
  .gitignore
  requirements.txt
  README.md
```

---

## 7. 설정 파일 설명

### 7.1 `config\watchlist.yaml`

시장 핵심 ETF, 변동성, 금리/크레딧, 섹터 ETF, 관심종목을 정의한다.

```yaml
market_core:
  - SPY
  - QQQ
  - IWM
  - DIA

volatility:
  - ^VIX

rates_credit:
  - TLT
  - HYG
  - UUP
  - ^TNX

sectors:
  - XLK
  - XLY
  - XLC
  - XLF
  - XLV
  - XLE
  - XLI
  - XLP
  - XLU
  - XLB
  - XLRE
  - SMH
  - SOXX

watchlist:
  - NVDA
  - AMD
  - AVGO
  - MSFT
  - AAPL
  - AMZN
  - META
  - GOOGL
  - TSLA
  - PLTR
  - COIN
  - NFLX
```

### 7.2 `config\settings.yaml`

프로그램 실행 기본값을 정의한다.

```yaml
session:
  default: "post_close"
  timezone_market: "America/New_York"
  timezone_user: "Asia/Seoul"

data:
  provider: "yfinance"
  lookback_period: "1y"
  interval: "1d"

events:
  earnings_provider: "alpha_vantage"
  economic_provider: "fmp_bls_fed"
  lookahead_days: 30
  earnings_risk_window_days: 7

output:
  max_priority_tickers: 7
  max_risk_tickers: 7
  language: "ko"

telegram:
  send_summary: true
  send_daily_packet: true
  send_gpt_prompt: true
  send_claude_prompt: true
```

### 7.3 `config\rules.yaml`

시장 모드별 행동 규칙, 금지 행동, 포지션 사이즈 축소 원칙을 정의한다.

```yaml
global_do_not_do:
  - "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지"
  - "D급 종목 물타기 금지"
  - "손절가 없는 진입 금지"
  - "VIX 상승 중 고베타 종목 포지션 확대 금지"
  - "CPI/FOMC/대형 실적 전후 과대 진입 금지"
  - "시장 모드 Caution/Defensive에서 신규 공격 매매 금지"
  - "뉴스 하나만 보고 차트·섹터 확인 없이 진입 금지"

risk_modes:
  risk_on:
    position_multiplier: 1.0
  mild_risk_on:
    position_multiplier: 0.8
  neutral:
    position_multiplier: 0.6
  caution:
    position_multiplier: 0.4
  defensive:
    position_multiplier: 0.2
```

### 7.4 `config\setups.yaml`

Breakout, Pullback, Avoid 셋업 규칙을 정의한다.

```yaml
setups:
  breakout:
    description: "전고점 또는 20일 고점 근처 돌파 후보"
    required:
      - "close_above_20dma"
      - "close_above_50dma"
      - "near_20d_high"
      - "volume_above_20d_avg"
    preferred:
      - "market_mode_not_defensive"
      - "sector_strong"
      - "relative_strength_vs_qqq_positive"

  pullback:
    description: "상승 추세 중 20일선 근처 눌림 후보"
    required:
      - "close_above_50dma"
      - "price_near_20dma"
      - "rsi_not_overheated"
    preferred:
      - "sector_not_weak"
      - "market_mode_not_defensive"

  avoid:
    description: "회피 또는 리스크 관리 대상"
    required_any:
      - "close_below_50dma"
      - "close_below_200dma"
      - "market_mode_defensive"
      - "major_event_high_impact"
```

### 7.5 `config\events_manual.yaml`

자동 이벤트 캘린더가 놓치는 항목을 수동 보정한다.

```yaml
manual_events:
  - date: "2026-05-14"
    time_et: "08:30"
    type: "macro"
    name: "CPI 세부 항목 확인"
    impact: "high"
    note: "자동 캘린더에는 CPI만 표시되지만, core/shelter 세부 항목 주의"

  - date: "2026-05-15"
    ticker: "NVDA"
    type: "company"
    name: "수동 확인 기업 이벤트"
    impact: "medium"
    note: "SAVE/TradingView에서 수동 확인"
```

### 7.6 `.env`

민감정보는 반드시 `.env`에만 저장한다.

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ALPHAVANTAGE_API_KEY=
FMP_API_KEY=
DATA_PROVIDER=yfinance
EVENT_PROVIDER=alpha_vantage_fmp_bls_fed
```

### 7.7 `.env.example`

Git에 올릴 수 있는 더미 예시 파일이다.

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
FMP_API_KEY=optional_fmp_key
DATA_PROVIDER=yfinance
EVENT_PROVIDER=alpha_vantage_fmp_bls_fed
```

---

## 8. 데이터 소스 설명

### 8.1 가격 데이터

MVP에서는 `yfinance`를 사용한다.

역할:

```text
- SPY, QQQ, IWM, DIA 가격
- 섹터 ETF 가격
- 관심종목 가격
- VIX, TLT, HYG, UUP, ^TNX 등 보조 데이터
```

주의:

```text
- yfinance는 Yahoo가 공식 보증하거나 승인한 도구가 아니다.
- MVP 검증용으로 사용한다.
- 실전 운영 안정성이 필요하면 유료 데이터 API로 전환 가능하게 설계한다.
```

### 8.2 어닝 데이터

1차 어닝 소스:

```text
Alpha Vantage EARNINGS_CALENDAR
```

역할:

```text
- 향후 3개월 어닝 캘린더 수집
- watchlist.yaml의 관심종목만 필터링
- 어닝 당일/익일/7일 이내 리스크 플래그 생성
```

### 8.3 경제 이벤트 데이터

경제 이벤트는 다음 순서로 사용한다.

```text
1. FMP Economic Calendar
2. BLS Calendar
3. Fed FOMC Calendar
4. events_manual.yaml
```

FMP는 통합 경제 캘린더 역할로 사용한다.  
BLS는 CPI, PPI, Employment Situation, JOLTS 등 노동/물가 지표의 공식 캘린더 역할로 사용한다.  
Fed FOMC Calendar는 FOMC 회의 일정, 의사록 공개일, SEP 포함 회의 여부를 확인하는 데 사용한다.

### 8.4 뉴스 맥락

뉴스 자동 수집은 MVP 범위에서 제외한다.

뉴스 맥락은 사용자가 다음 소스에서 직접 확인한다.

```text
- SAVE / 세이브티커
- TradingView 개별 티커 뉴스
- TradingView News Flow
- 직접 확인한 기업/시장 뉴스
```

확인한 뉴스는 필요한 경우 `data\manual_news_notes.md`에 입력한다.

### 8.5 TradingView

MVP에서 TradingView는 자동 데이터 백엔드가 아니다.

사용 방식:

```text
- 차트 수동 확인
- 개별 티커 뉴스 수동 확인
- VIX 수동 확인
- Screener 수동 export
- Pine Screener 수동 확인
```

금지 방식:

```text
- TradingView 웹페이지 scraping
- 로그인 자동화
- 비공식 API 사용
- 내부 WebSocket 사용
- 유료 계정을 데이터 API처럼 우회 사용
```

---

## 9. 이벤트/어닝 자동화 설계

### 9.1 이벤트 모듈 구성

```text
src\event_sources.py
src\event_calendar.py
```

### 9.2 `event_sources.py` 역할

```text
- fetch_alpha_vantage_earnings()
- fetch_fmp_economic_calendar()
- fetch_bls_calendar()
- fetch_fomc_calendar()
- normalize_event()
```

### 9.3 `event_calendar.py` 역할

```text
- load_watchlist()
- load_manual_events()
- collect_auto_events()
- filter_relevant_events()
- merge_auto_and_manual_events()
- assign_event_impact()
- create_event_risk_flags()
- save_events_auto_json()
- save_events_merged_json()
```

### 9.4 어닝 자동화 흐름

```text
Alpha Vantage EARNINGS_CALENDAR
  ↓
CSV 다운로드
  ↓
DataFrame 변환
  ↓
watchlist.yaml의 관심종목만 필터링
  ↓
어닝 날짜, 티커, 예상 EPS 등 저장
  ↓
어닝 7일 이내 리스크 플래그 생성
```

### 9.5 경제 이벤트 자동화 흐름

```text
FMP Economic Calendar
  ↓
미국 이벤트 필터링
  ↓
고영향 이벤트 필터링
  ↓
BLS Calendar로 CPI/PPI/Employment/JOLTS 보강
  ↓
Fed FOMC Calendar로 FOMC/Minutes/SEP 회의 보강
  ↓
events_manual.yaml과 병합
```

### 9.6 이벤트 중요도 분류

```text
High:
- CPI
- PPI
- Employment Situation / Nonfarm Payrolls
- FOMC Rate Decision
- FOMC Minutes
- PCE Price Index
- GDP
- 대형 관심종목 어닝

Medium:
- JOLTS
- Retail Sales
- ISM
- Consumer Confidence
- Fed Speaker
- Treasury Auction

Low:
- 일반 통계
- 관심종목과 직접 관련 낮은 이벤트
```

### 9.7 이벤트 리스크 플래그

```text
macro_high_today
macro_high_next_24h
fomc_today
fomc_minutes_today
earnings_today
earnings_tomorrow
earnings_within_7d
manual_event_high
```

### 9.8 이벤트 출력 예시

```json
{
  "date": "2026-05-12",
  "events_today": [
    {
      "type": "macro",
      "name": "Consumer Price Index",
      "time_et": "08:30",
      "impact": "high",
      "source": "BLS"
    }
  ],
  "earnings_watchlist_7d": [
    {
      "type": "earnings",
      "ticker": "NVDA",
      "date": "2026-05-22",
      "timing": "unknown",
      "impact": "high",
      "source": "Alpha Vantage",
      "risk_flag": "earnings_within_7d"
    }
  ]
}
```

---

## 10. 시장 모드 판정 규칙

### 10.1 시장 모드 종류

```text
Risk-On
Mild Risk-On
Neutral
Caution
Defensive
```

### 10.2 입력 데이터

```text
SPY
QQQ
IWM
DIA
SMH
XLK
TLT
HYG
UUP
^VIX
^TNX
```

### 10.3 점수 규칙

긍정 점수:

```text
+1: SPY가 20일선 위
+1: QQQ가 20일선 위
+1: SPY가 50일선 위
+1: QQQ가 50일선 위
+1: QQQ가 SPY보다 5일 상대강도 우위
+1: SMH가 QQQ보다 5일 상대강도 우위
+1: VIX가 전일 대비 하락
+1: HYG가 20일선 위
```

부정 점수:

```text
-1: SPY가 50일선 아래
-1: QQQ가 50일선 아래
-1: IWM이 SPY보다 5일 상대강도 약세
-1: VIX가 전일 대비 5% 이상 상승
-1: VIX가 20일선 위
-1: TLT 약세 + QQQ 약세
-1: 방어 섹터만 강함
```

### 10.4 점수 해석

```text
+5 이상: Risk-On
+2 ~ +4: Mild Risk-On
-1 ~ +1: Neutral
-4 ~ -2: Caution
-5 이하: Defensive
```

### 10.5 이벤트 오버레이

시장 모드가 Risk-On이어도 이벤트 리스크가 크면 `event_overlay`를 붙인다.

예:

```text
Market Mode: Mild Risk-On
Event Overlay: Caution
Reason: CPI 발표 당일
```

오버레이 규칙:

```text
High-impact macro event today → Caution overlay
FOMC decision day → Caution overlay
FOMC minutes day → Caution overlay
대형 관심종목 어닝 당일 → ticker-specific caution
VIX 급등 → Defensive bias
```

---

## 11. 관심종목 A/B/C/D 랭킹 규칙

### 11.1 점수 규칙

긍정 점수:

```text
+2: 종가가 20일선 위
+2: 종가가 50일선 위
+1: 종가가 200일선 위
+1: 20일선이 50일선 위
+1: 거래량이 20일 평균보다 큼
+1: 최근 20일 고점 근처
+1: SPY보다 최근 5일 상대강도 우위
+1: QQQ보다 최근 5일 상대강도 우위
+1: 관련 섹터 ETF가 강함
```

부정 점수:

```text
-2: 종가가 50일선 아래
-2: 종가가 200일선 아래
-1: 거래량 동반 하락
-1: 최근 20일 저점 근처
-1: VIX 상승 중 고베타 종목
-1: 주요 이벤트 7일 이내
-2: 어닝 당일 또는 익일
```

### 11.2 등급 기준

```text
A급: 7점 이상
B급: 4~6점
C급: 1~3점
D급: 0점 이하
```

### 11.3 등급 의미

```text
A급:
- 우선 관찰
- 셋업 후보
- 단, 이벤트 리스크 있으면 주의 표시

B급:
- 조건부 관찰
- 명확한 가격 행동 확인 필요

C급:
- 대기
- 명확한 셋업 전까지 보류

D급:
- 회피/주의
- 물타기 금지
- 반등 예측 금지
```

### 11.4 결과 출력 형식

```json
{
  "ticker": "NVDA",
  "grade": "A",
  "score": 8,
  "positive_reasons": [
    "20일선 위",
    "50일선 위",
    "20일 고점 근처",
    "QQQ 대비 상대강도 우위"
  ],
  "negative_reasons": [
    "어닝 7일 이내"
  ],
  "event_flags": [
    "earnings_within_7d"
  ]
}
```

---

## 12. 셋업 후보 분류 규칙

### 12.1 Breakout 후보

조건:

```text
- 20일선 위
- 50일선 위
- 20일 고점 근처
- 거래량 20일 평균 이상
- 시장 모드가 Defensive가 아님
- 가능하면 섹터가 강함
```

출력:

```text
Breakout 후보:
- NVDA: 20일 고점 근처, 거래량 증가, 섹터 강세
```

### 12.2 Pullback 후보

조건:

```text
- 50일선 위
- 20일선 근처
- 과열이 어느 정도 해소됨
- 섹터가 약하지 않음
- 시장 모드가 Defensive가 아님
```

출력:

```text
Pullback 후보:
- MSFT: 50일선 위, 20일선 근처, 추세 훼손 없음
```

### 12.3 Avoid 후보

조건:

```text
- 50일선 아래
- 200일선 아래
- 최근 20일 저점 근처
- 시장 모드 Defensive
- 어닝 당일/익일
- 고영향 이벤트 직전
```

출력:

```text
Avoid 후보:
- TSLA: 50일선 아래, 변동성 확대, 이벤트 리스크
```

---

## 13. 리스크 엔진과 금지 행동

### 13.1 리스크 엔진 입력

```text
- 시장 모드
- 이벤트/어닝 데이터
- 관심종목 등급
- VIX 상태
- 수동 뉴스 메모
- rules.yaml
```

### 13.2 리스크 엔진 출력

```text
- risk_warnings
- do_not_do_list
- no_trade_flags
- ticker_specific_risks
```

### 13.3 핵심 리스크 경고

```text
시장 모드 Caution/Defensive:
- 신규 공격 매매 제한
- 포지션 사이즈 축소
- A급 종목만 관찰

VIX 상승:
- 고베타 종목 포지션 확대 금지
- 장초반 추격 금지

High-impact macro event today:
- 이벤트 전후 신규 진입 주의
- 첫 반응 추격 금지
- 발표 후 방향성 확인 필요

Earnings within 7 days:
- 스윙 진입 주의
- 변동성 확대 가능성 표시

D급 종목:
- 물타기 금지
- 반등 예측 금지
```

### 13.4 매일 출력할 금지 행동

```text
1. 장초반 첫 5~15분 갭상승 종목 무근거 추격 금지
2. D급 종목 물타기 금지
3. 손절가 없는 진입 금지
4. VIX 상승 중 고베타 종목 포지션 확대 금지
5. CPI/FOMC/대형 실적 전후 과대 진입 금지
6. 시장 모드 Caution/Defensive에서 신규 공격 매매 금지
7. 뉴스 하나만 보고 차트·섹터 확인 없이 진입 금지
```

### 13.5 No-trade Flag

아래 조건이 복수로 발생하면 `No-trade / Observation Bias`를 표시한다.

```text
- Defensive 모드
- VIX 급등
- High-impact macro event today
- 관심종목 대부분 C/D급
- QQQ와 SPY 방향 불일치
- SMH 약세
- D급 종목만 급등
```

---

## 14. Daily Packet 구조

`output\daily_packet.md`는 GPT/Claude와 사용자가 모두 읽기 좋은 구조로 생성한다.

```markdown
# Personal Trading OS Daily Packet

Date:
Session:
Timezone:
Generated At:

## 1. Market Regime

- Mode:
- Score:
- Event Overlay:
- Summary:

### Positive Evidence
-

### Negative Evidence
-

## 2. Event Risk

### Today
-

### Next 24 Hours
-

### Watchlist Earnings Within 7 Days
-

### Manual Events
-

## 3. Watchlist Ranking

### A Grade - Priority Watch
-

### B Grade - Secondary Watch
-

### C Grade - Wait
-

### D Grade - Avoid / Risk
-

## 4. Setup Candidates

### Breakout
-

### Pullback
-

### Avoid
-

## 5. Risk Warnings

-

## 6. Today's Do-Not-Do List

1.
2.
3.
4.
5.

## 7. Manual News Notes

-

## 8. Questions for GPT / Claude

1.
2.
3.

## 9. Data Quality Notes

- Missing:
- Delayed:
- Fallback Used:
```

`daily_packet.json`은 같은 내용을 구조화된 JSON으로 저장한다.

---

## 15. GPT/Claude 프롬프트 생성 방식

### 15.1 ChatGPT Pro용 프롬프트

파일:

```text
output\prompt_for_gpt.txt
```

목적:

```text
Daily Packet을 기반으로 오늘의 트레이딩 플랜을 생성한다.
```

프롬프트 핵심 규칙:

```text
- 데이터에 없는 숫자, 가격, 뉴스, 날짜를 만들지 말 것
- 매수/매도 단정 금지
- 투자 조언처럼 표현하지 말 것
- Bull / Neutral / Bear 시나리오로 나눌 것
- 우선순위 종목과 피해야 할 종목을 정리할 것
- 오늘 금지 행동을 명확히 표시할 것
- SAVE/TradingView에서 확인해야 할 뉴스 항목을 표시할 것
```

### 15.2 Claude Max용 프롬프트

파일:

```text
output\prompt_for_claude.txt
```

목적:

```text
ChatGPT가 만든 트레이딩 플랜 또는 Daily Packet 자체를 리스크 리뷰한다.
```

프롬프트 핵심 규칙:

```text
- 과잉확신 탐지
- 데이터에 없는 추정 탐지
- 뉴스와 가격 움직임의 단정적 연결 탐지
- 장초반 추격 위험 탐지
- VIX/시장 모드/이벤트와 충돌하는 아이디어 탐지
- 반대 시나리오 제시
- 보수적 체크리스트 제시
```

### 15.3 LLM API 사용 금지

MVP에서는 다음을 하지 않는다.

```text
- OpenAI API 호출
- Claude API 호출
- ChatGPT/Claude 웹 UI 자동화
- 브라우저 자동 로그인
- 결과 자동 scraping
```

GPT Pro와 Claude Max는 사람이 직접 붙여넣고 검토하는 방식으로 사용한다.

---

## 16. Telegram 전송 방식

### 16.1 전송 파일

Telegram으로 전송할 항목은 다음과 같다.

```text
1. output\telegram_summary.txt → sendMessage
2. output\daily_packet.md → sendDocument
3. output\prompt_for_gpt.txt → sendDocument
4. output\prompt_for_claude.txt → sendDocument
```

### 16.2 메시지 정책

```text
- Telegram 요약 메시지는 짧게 유지한다.
- 긴 내용은 파일로 전송한다.
- 메시지가 길면 4000자 단위로 나눠서 전송한다.
- Markdown 파싱 오류를 피하기 위해 기본 텍스트 전송을 우선한다.
```

### 16.3 Telegram 요약 예시

```text
🇺🇸 Personal Trading OS

Date: 2026-05-12
Session: Post-close

시장 모드:
- Mild Risk-On
- Event Overlay: Caution

우선 관찰:
A급: NVDA, AMD
B급: MSFT, META

주의:
D급: TSLA, COIN

오늘 이벤트:
- CPI 08:30 ET
- NVDA 어닝 7일 이내

오늘 금지:
1. 장초반 추격 금지
2. D급 물타기 금지
3. 이벤트 전후 과대 진입 금지

첨부:
- daily_packet.md
- prompt_for_gpt.txt
- prompt_for_claude.txt
```

---

## 17. Windows Task Scheduler 운영 방식

### 17.1 실행 파일

`run_post_close.bat`

```bat
@echo off
cd /d C:\trading\personal_trading_os

echo [%date% %time%] Starting post-close run >> logs\post_close.log

.venv\Scripts\python.exe src\main.py --session post_close >> logs\post_close.log 2>&1

echo [%date% %time%] Finished post-close run >> logs\post_close.log
```

`run_pre_market.bat`는 2차 단계에서 사용한다.

```bat
@echo off
cd /d C:\trading\personal_trading_os

echo [%date% %time%] Starting pre-market run >> logs\pre_market.log

.venv\Scripts\python.exe src\main.py --session pre_market >> logs\pre_market.log 2>&1

echo [%date% %time%] Finished pre-market run >> logs\pre_market.log
```

### 17.2 Task Scheduler 등록

Post-close 리포트는 한국 시간 기준 화~토 오전 06:50에 실행한다.

```cmd
schtasks /Create /TN "PersonalTradingOS_PostClose" /TR "C:\trading\personal_trading_os\run_post_close.bat" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 06:50 /F
```

수동 실행 테스트:

```cmd
schtasks /Run /TN "PersonalTradingOS_PostClose"
```

로그 확인:

```powershell
type C:\trading\personal_trading_os\logs\post_close.log
```

### 17.3 운영 원칙

```text
- 자동 실행은 Windows Task Scheduler가 담당한다.
- venv activate는 하지 않는다.
- .venv\Scripts\python.exe를 직접 호출한다.
- 모든 로그는 logs\ 폴더에 저장한다.
- 실패해도 Telegram 또는 로그에 실패 원인을 남긴다.
```

---

## 18. GPT 프로젝트 폴더 운영 방식

### 18.1 GPT 프로젝트의 역할

GPT 프로젝트 폴더는 이 프로젝트의 총괄 작업공간이다.

역할:

```text
- 전체 기획 보관
- 프로젝트 기준 문서 보관
- 코딩 프롬프트 보관
- 생성 코드 검토
- 오류 로그 분석
- Daily Packet 개선
- GPT/Claude 프롬프트 개선
- 운영 후 변경 사항 관리
```

### 18.2 프로젝트에 보관할 문서

```text
00_PROJECT_SPEC.md
01_RUNBOOK_WINDOWS.md
02_ARCHITECTURE.md
03_PROMPT_LIBRARY.md
04_RULES_AND_SCORING.md
05_DATA_SOURCES.md
06_CODE_REVIEW_CHECKLIST.md
07_CHANGELOG.md
```

### 18.3 채팅창 운영 방식

권장 채팅창 구조:

```text
[00] 총괄 기획 / PM 채팅
[01] PROJECT_SPEC 문서 생성
[02] Windows 프로젝트 스캐폴딩
[03] 가격 데이터 + 지표 계산 모듈
[04] 이벤트/어닝 자동화 모듈
[05] 시장 모드 + 관심종목 랭킹
[06] Daily Packet + 프롬프트 생성
[07] Telegram + Windows Task Scheduler
[08] Claude 코드 리뷰 / 리팩터링
[09] 디버깅 전용
[10] 운영 후 개선 / 프롬프트 튜닝
```

### 18.4 새 채팅창 시작 방식

새 채팅창을 열 때는 다음을 지킨다.

```text
1. 00_PROJECT_SPEC.md를 첨부하거나 요약을 붙여넣는다.
2. 한 채팅창에서는 한 모듈만 다룬다.
3. 파일 단위로 전체 코드를 요청한다.
4. 작업 완료 후 CHANGELOG에 반영할 요약을 요청한다.
5. 디버깅 채팅에는 오류 로그와 실행 명령을 반드시 포함한다.
```

---

## 19. Claude Max / Claude Code 활용 방식

### 19.1 Claude Max 역할

Claude Max는 다음 역할로 사용한다.

```text
- 코드 리뷰
- 리팩터링
- 긴 코드베이스 검토
- 예외 처리 누락 확인
- Windows 경로 문제 확인
- 시장 모드 로직 과민/둔감 문제 검토
- 리스크 엔진 검토
- Daily Packet 출력 품질 검토
```

### 19.2 Claude Project 구성

Claude Project 이름:

```text
Personal Trading OS Code Review
```

업로드할 문서:

```text
00_PROJECT_SPEC.md
02_ARCHITECTURE.md
04_RULES_AND_SCORING.md
06_CODE_REVIEW_CHECKLIST.md
```

### 19.3 Claude Code 사용 시 주의

Claude Code를 사용할 경우 다음을 확인한다.

```powershell
echo $env:ANTHROPIC_API_KEY
```

`ANTHROPIC_API_KEY`가 설정되어 있으면 API 과금 방식으로 동작할 수 있으므로, Claude Max 구독 기반 사용 여부를 확인한다.

### 19.4 Claude 리뷰 요청 기준

Claude에게 코드를 리뷰할 때는 다음을 요청한다.

```text
1. 구조적 문제
2. Windows 경로 문제
3. 예외 처리 누락
4. API 실패 fallback 누락
5. 민감정보 노출 가능성
6. 시장 모드 점수 과민성
7. 관심종목 랭킹 로직 오류
8. 테스트 케이스 누락
9. 유지보수성 문제
10. 운영 중 깨질 가능성이 높은 지점
```

---

## 20. 1차 MVP 완성 기준

1차 MVP는 아래 조건을 만족하면 완료로 본다.

```text
1. Windows에서 Python 3.12 가상환경이 정상 동작한다.
2. C:\trading\personal_trading_os 구조가 생성되어 있다.
3. config 파일들이 작성되어 있다.
4. yfinance 기반 가격 데이터가 수집된다.
5. 20DMA, 50DMA, 200DMA, 거래량 지표가 계산된다.
6. Alpha Vantage 어닝 캘린더가 수집된다.
7. 경제 이벤트가 FMP/BLS/Fed 중 최소 하나 이상에서 수집된다.
8. events_manual.yaml과 자동 이벤트가 병합된다.
9. 시장 모드가 5단계 중 하나로 판정된다.
10. 관심종목이 A/B/C/D로 분류된다.
11. Breakout/Pullback/Avoid 후보가 생성된다.
12. 리스크 경고와 금지 행동이 생성된다.
13. daily_packet.md가 생성된다.
14. daily_packet.json이 생성된다.
15. prompt_for_gpt.txt가 생성된다.
16. prompt_for_claude.txt가 생성된다.
17. telegram_summary.txt가 생성된다.
18. Telegram으로 요약 메시지와 파일이 전송된다.
19. run_post_close.bat가 정상 실행된다.
20. Windows Task Scheduler에서 자동 실행된다.
21. logs\post_close.log에 실행 로그가 남는다.
22. ChatGPT Pro에 prompt_for_gpt.txt를 넣으면 트레이딩 플랜이 생성된다.
23. Claude Max에 prompt_for_claude.txt를 넣으면 리스크 리뷰가 생성된다.
24. 사용자가 매일 “오늘 볼 종목”과 “오늘 피해야 할 행동”을 빠르게 확인할 수 있다.
```

---

## 21. 향후 확장 계획

### 21.1 2차 기능

```text
1. TradingView Screener CSV import
2. /risk 명령어: 진입가/손절가 기준 포지션 사이즈 계산
3. /plan TICKER 명령어: 특정 종목 매매 전 체크리스트
4. /journal 명령어: 매매일지 저장
5. Weekly Review: 한 주 복기 자동 생성
6. SEC filing alert: 관심종목 8-K, 10-Q, 10-K 감지
7. 프리마켓 리포트 추가
```

### 21.2 3차 기능

```text
1. 포트폴리오 노출도 대시보드
2. 섹터/테마 집중도 계산
3. 주간 실수 패턴 분석
4. Claude Max용 주간 복기 패킷 생성
5. 차트 이미지/수동 메모 기반 매매일지
6. TradingView Screener/Pine Screener CSV 자동 import 보조
```

### 21.3 장기 확장

```text
1. 유료 가격 데이터 API 전환
2. Notion 또는 Google Sheet 저장
3. Supabase/Postgres DB 도입
4. Telegram inline 버튼
5. Telegram 명령어 기반 인터랙션
6. 장중 What Changed? 기능
7. Opening Range Tracker
8. Gap Tracker
9. Position Sizing Dashboard
```

### 21.4 계속 제외할 항목

아래는 장기적으로도 신중하게 접근한다.

```text
- 자동매매
- 브로커 주문 API
- TradingView scraping
- ChatGPT/Claude 웹 UI 자동화
- 유료 구독 계정을 API처럼 우회 사용하는 방식
```

---

## 부록 A. 핵심 설계 원칙

```text
1. 데이터 수집과 계산은 코드가 한다.
2. 해석과 문장화는 GPT/Claude가 수동 보조한다.
3. 뉴스는 좋은 소스를 사람이 선별한다.
4. 자동화는 반복 업무에만 적용한다.
5. 매매 결정은 사용자가 한다.
6. 프로그램은 수익을 보장하지 않는다.
7. 프로그램은 실수 방지와 준비 품질 향상을 목표로 한다.
```

---

## 부록 B. MVP의 한 줄 정의

```text
Personal Trading OS MVP는 Windows에서 매일 자동 실행되어 미국장 가격/이벤트/관심종목 상태를 정리하고, Telegram으로 Daily Packet과 GPT/Claude용 프롬프트를 보내주는 개인 트레이딩 운영 보조 시스템이다.
```

---

## 부록 C. 참고한 공식/주요 문서

이 문서는 다음 공식 또는 주요 문서의 기능 설명을 기준으로 설계되었다.

```text
- Python Developer’s Guide: Python version support status
- yfinance documentation: Yahoo Finance API data usage disclaimer
- Alpha Vantage API documentation: Fundamental Data / Earnings Calendar
- Financial Modeling Prep documentation: Economic Calendar API
- U.S. Bureau of Labor Statistics: Schedule of Selected Releases
- Federal Reserve: FOMC meeting calendars and information
- Telegram Bot API: sendMessage, sendDocument
- OpenAI Help Center: Projects in ChatGPT
```
