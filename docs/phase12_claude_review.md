# Phase 12 코드 리뷰 — Personal Trading OS MVP

리뷰 일자: 2026-05-13  
리뷰어: Claude Sonnet 4.6  
브랜치: phase12-review  
리뷰 방식: 읽기 전용 (코드 수정 없음)

---

## 전체 판정: 조건부 가능 (Conditionally Operational)

시스템은 end-to-end로 실행되고 모든 출력 파일이 생성된다 (로그 확인). Telegram 전송도 성공한다. 그러나 **지표 계산 파이프라인 전체가 fallback 경로로 동작 중**이며, 이로 인해 market regime 점수가 구조적으로 낮게 산출되고, daily_packet.md의 핵심 섹션이 오표시된다. 또한 외부 API 이벤트 수집이 전면 실패 상태이므로, 손으로 심은 이벤트에만 의존하고 있다. 이 상태로 실전 운영하면 **잘못된 시장 판단을 올바른 것으로 신뢰할 위험**이 있다.

---

## High 이슈 (즉시 수정 필요)

### H1 — `fetch_prices → indicators` 데이터 형식 불일치

- **파일:** `src/fetch_prices.py`, `src/indicators.py`
- **문제:** `fetch_prices.py`는 `dict[str, list[dict]]` (records 형식)를 반환하지만 `indicators.py`의 `calculate_indicators_for_tickers()`는 `dict[str, pd.DataFrame]`을 기대한다. 형식 불일치 시 각 ticker가 **조용히 실패(silent fail)**하며 빈 dict를 반환한다.
- **결과:** `main.py`가 항상 `fallback_calculate_indicators()`로 강제 진입. `data_quality_notes`에 `"SPY: 20DMA unavailable."` 등이 기록되어 있어 실제 확인됨 (`output/daily_packet.json`).
- **영향 범위:** 모든 MA 기반 스코어링 신호 비활성화, `market_regime`, `watchlist_ranker`, `setup_matcher` 전체 정확도 저하.

### H2 — Fallback 지표 필드명 vs `market_regime.py` 패턴 불일치

- **파일:** `src/main.py` (`fallback_calculate_indicators`), `src/market_regime.py` (`_ma_value`)
- **문제:** fallback은 `dma20`, `dma50`, `dma200`을 출력한다. `market_regime.py`의 `_ma_value(row, period)`는 `f"{period}DMA"` (`20DMA`), `f"dma_{period}"` (`dma_20`) 패턴을 탐색하지만 `dma20` (구분자 없음)은 탐색하지 않는다.
- **결과:** fallback 경로에서 MA 신호가 항상 0점 처리. 현재 로그의 시장 모드 점수 `2`는 실제 가능한 점수보다 낮을 가능성이 높다.
- **확인:** `output/daily_packet.json`의 `data_quality_notes` 전 ticker에 `20DMA unavailable` 기록.

### H3 — `positive_evidence` 키 불일치로 Daily Packet 오표시

- **파일:** `src/main.py` (`fallback_render_daily_packet`), `src/market_regime.py`
- **문제:** `determine_market_regime()`은 `positive_reasons` 키를 반환한다. `fallback_render_daily_packet()`은 `market.get("positive_evidence", [])` 키를 읽는다. 키가 다르므로 항상 빈 리스트 반환.
- **결과:** `output/daily_packet.md` Section 2에 "Positive Evidence: - 없음" 표시. 실제로는 `output/daily_packet.json`에 `positive_reasons: ["QQQ가 SPY보다 5일 상대강도 우위", ...]` 3개 근거가 있음.
- **사용자 영향:** 트레이더가 매일 "긍정 근거 없음"을 보고 잘못된 판단을 할 수 있음.

### H4 — 이벤트 `risk_flags` 날짜 필터링 없음 (FOMC 조기 경보 버그)

- **파일:** `src/market_regime.py` (`_collect_event_flags`), `src/risk_engine.py` (`_normalize_events`)
- **문제:** `events_merged.json`의 May 20 FOMC Minutes 이벤트에 `risk_flags: ["fomc_minutes_today"]`가 설정되어 있다. 두 모듈 모두 이벤트 날짜 필터링 없이 모든 이벤트의 `risk_flags`를 수집한다.
- **결과:** 오늘(May 13)에 "FOMC Minutes 이벤트 당일" 경고가 출력됨. 1주일 이른 경보.
- **구조적 원인:** 이벤트 `risk_flags` 필드명이 절대적 날짜 의미("today")를 내포하고 있지만, 처리 시 날짜 체크가 없음.

### H5 — 외부 API 이벤트 수집 전면 실패

- **파일:** `src/event_sources.py`, `output/events_auto.json`
- **문제:** `events_auto.json`에서 확인된 상태:
  - `alpha_vantage_earnings`: `skipped_missing_api_key`
  - `fmp_economic_calendar`: `skipped_missing_api_key`
  - `bls_calendar`: `failed_http` (403 Forbidden)
  - `fed_fomc_calendar`: `ok_no_events` (실제 FOMC 일정 없어서 빈 결과)
- **결과:** `events: []` — 자동 수집 이벤트 0건. 모든 어닝/매크로 이벤트가 수동으로 심은 데이터에만 의존.
- **MVP 충족 여부:** 스펙 `EVENT_PROVIDER=alpha_vantage_fmp_bls_fed` 조건 미충족.

---

## Medium 이슈

### M1 — Breakout/Pullback 셋업이 항상 비어 있음

- **파일:** `src/setup_matcher.py`, `config/setups.yaml`
- **문제:** `reject_if: ["high_impact_macro_today"]` 조건이 Breakout/Pullback 양쪽에 설정되어 있다. 현재 `events_merged.json`의 top-level `risk_flags`에 `macro_high_today`가 상시 설정되어 있어 모든 셋업이 거부됨.
- **부가 문제:** fallback 지표에서 `near_20d_high`, `volume_above_20d_avg` 같은 불리언 필드가 올바르게 계산되는지 확인 필요.
- **사용자 영향:** 매일 "발굴된 셋업 없음"으로 이 섹션이 사실상 무기능.

### M2 — Daily Packet Section 7이 오늘 노트가 아닌 전체 파일 내용 출력

- **파일:** `src/main.py` (`fallback_render_daily_packet`), `src/config_loader.py`
- **문제:** `config_loader.py`는 `manual_news_notes.md` 전체를 로드하고, `fallback_render_daily_packet()`은 `state.manual_news_notes`를 날짜 필터링 없이 그대로 삽입한다. `packet_builder.py`의 `_read_manual_news_notes()`는 `_extract_dated_markdown_section()`으로 날짜 필터링을 하지만 fallback 경로에서는 호출되지 않는다.
- **결과:** Section 7에 템플릿/README 포함 전체 파일이 노출됨.

### M3 — `run_pre_market.bat` 미존재

- **파일:** 프로젝트 루트
- **문제:** 스펙과 런북에서 언급되는 `run_pre_market.bat`가 존재하지 않는다.
- **영향:** pre-market 세션 Task Scheduler 등록 불가. 시스템이 post-close 세션만 운영 가능한 상태.

### M4 — `MOCK_MODE=true` 기본값, 동작 미문서화

- **파일:** `src/config_loader.py`, `.env.example`
- **문제:** `config_loader.py`에서 `MOCK_MODE`의 기본값이 `"true"`로 하드코딩되어 있다 (`os.getenv("MOCK_MODE", "true")`). 스펙에 `MOCK_MODE`에 대한 언급 없음. 실제로 이 값이 코드 어디서 분기를 만드는지 명확히 추적되지 않음.
- **위험:** 실전 운영 시 MOCK_MODE가 활성화된 채 돌 수 있음. 의도치 않게 mock 데이터가 사용될 가능성.

---

## Low 이슈

### L1 — Telegram 요약에 Do-Not-Do 항목 5개만 표시 (7개 중)

- **파일:** `src/telegram_sender.py` 또는 `src/packet_builder.py` (요약 생성 경로)
- **문제:** `output/telegram_summary.txt`에 금지 행동이 5개만 출력됨. 리스크 엔진은 `REQUIRED_DO_NOT_DO` 7개를 항상 포함하나, 요약 렌더링 과정에서 2개가 누락됨.
- **영향:** 트레이더가 매일 5개만 확인하게 됨.

### L2 — 이벤트 리스크 플래그가 한국어가 아닌 raw 문자열로 출력

- **파일:** `src/telegram_sender.py` 또는 요약 렌더링 함수
- **문제:** `telegram_summary.txt`의 "이벤트 리스크" 섹션이 `macro_high_next_24h`, `macro_high_today`를 그대로 출력함.
- **개선:** `"macro_high_today"` → `"오늘 고임팩트 매크로 이벤트 있음"` 등 한국어 매핑 필요.

### L3 — `.env.example` 미문서화 항목

- **파일:** `.env.example`
- **문제:** `MOCK_MODE=true`가 스펙 어디에도 언급되지 않음. 새 설치 사용자가 이 값의 의미를 알 수 없음.

---

## 리뷰 목표별 판정 요약

| # | 목표 | 판정 |
|---|------|------|
| 1 | MVP 스펙 충족 | 부분 충족 — 실행·출력 파일은 생성되나 지표·이벤트 품질 미달 |
| 2 | Windows 실행 가능 | 충족 — bat 파일, 경로, 인코딩 모두 올바름 |
| 3 | 경로/인코딩/로그 안전성 | 충족 — `chcp 65001`, `PYTHONUTF8=1`, 프리체크 모두 정상 |
| 4 | .env 민감정보 노출 | 충족 — 토큰 로그/출력 미노출, `dotenv_values()` 사용 |
| 5 | yfinance 실패 시 프로그램 생존 | 충족 — per-ticker 격리, fallback 경로 작동 |
| 6 | 이벤트 수집 실패 fallback | 부분 충족 — fallback 로직은 있으나 수동 데이터에 의존 중 |
| 7 | events_merged.json 일관 사용 | 부분 충족 — 구조는 일관되나 날짜 필터링 누락 |
| 8 | 시장 모드 점수 과민/둔감 | 과소 평가 — MA 신호 비활성화로 점수 구조적 저평가 |
| 9 | 리스크 엔진 금지 행동 출력 | 부분 충족 — 7개 생성되나 5개만 전달됨 |
| 10 | Daily Packet 가독성 | 부분 충족 — 긍정 근거 오표시, Section 7 오출력 |
| 11 | Telegram 실패 로깅 | 충족 — 모든 예외 catch + 로그 기록 |
| 12 | pytest 테스트 커버리지 | 부분 충족 — 핵심 로직 커버, 파이프라인 통합 테스트 없음 |
| 13 | 금지 코드 부재 | 충족 — 자동매매/스크래핑/LLM API 코드 없음 |
| 14 | 운영 중 가장 깨지기 쉬운 곳 | H1, H4, H5 |

---

## 반드시 고칠 것 (Must-Fix)

우선순위 순:

**1. H1 — `fetch_prices` → `indicators` 형식 변환** (`src/fetch_prices.py` 또는 `src/indicators.py`)
- `fetch_prices.py`가 반환하는 `list[dict]`를 `pd.DataFrame`으로 변환하는 어댑터 추가, 또는 `indicators.py`가 두 형식을 모두 수용하도록 수정.
- 이 버그가 H2, M1, M4를 연쇄 유발하는 **근본 원인**.

**2. H2 — Fallback 지표 필드명 통일** (`src/main.py` 또는 `src/market_regime.py`)
- `fallback_calculate_indicators()`의 출력을 `20DMA`, `50DMA`, `200DMA`로 변경, 또는 `market_regime.py`의 `_ma_value()`가 `dma20` 패턴도 인식하도록 수정.
- H1 수정 후에도 fallback 경로가 유지될 수 있으므로 독립적으로 수정 필요.

**3. H3 — `positive_evidence` 키 수정** (`src/main.py`)
- `fallback_render_daily_packet()` 내 `market.get("positive_evidence", [])` → `market.get("positive_reasons", [])`으로 변경.
- 1줄 수정.

**4. H4 — 이벤트 날짜 필터링** (`src/market_regime.py`, `src/risk_engine.py`)
- `_collect_event_flags()`와 `_normalize_events()`에서 각 이벤트의 날짜를 today와 비교하는 필터 추가.
- `risk_flags: ["fomc_minutes_today"]`는 해당 이벤트 날짜 당일에만 활성화.

**5. M2 — Section 7 날짜 필터링** (`src/main.py`)
- `fallback_render_daily_packet()`에서 `_extract_dated_markdown_section()` 호출하도록 수정.

---

## 나중에 고쳐도 되는 것 (Can-Fix-Later)

- **H5 — API 키 설정 및 BLS 403 대응:** `.env`에 실제 API 키 입력, BLS endpoint 변경 대응. 수동 이벤트가 현재 충분히 기능하고 있으므로 급하지 않음.
- **H6 — events_merged.json top-level risk_flags 재생성 로직:** 매 실행 시 날짜 기반으로 동적 재계산하도록 이벤트 캘린더 모듈 수정.
- **M1 — Breakout/Pullback 셋업 복구:** H1, H4 수정 후 near_20d_high, volume_above_20d_avg 필드 생성 여부 재검증.
- **M3 — `run_pre_market.bat` 생성:** 런북 기준 템플릿 그대로 작성. `--session pre_market` 인자만 다름.
- **M4 — MOCK_MODE 문서화 및 기본값 수정:** 기본값을 `"false"`로 변경하고 `.env.example`과 런북에 설명 추가.
- **L1 — Telegram Do-Not-Do 7개 전달:** 요약 렌더링 함수에서 잘림 조건 수정.
- **L2 — risk_flags 한국어 매핑 딕셔너리 추가.**
- **L3 — `.env.example` MOCK_MODE 주석 추가.**

---

## 테스트 보강 제안

현재 테스트의 가장 큰 공백은 **모듈 간 데이터 형식 계약**이다.

| 우선순위 | 테스트 대상 | 구체적 내용 |
|----------|-------------|-------------|
| 필수 | `fetch_prices → indicators` 통합 | `fetch_prices`가 반환하는 dict를 직접 `calculate_indicators_for_tickers()`에 넣어 빈 결과가 아닌 정상 지표가 나오는지 확인 |
| 필수 | `fallback_calculate_indicators` 필드명 | 출력 dict에 `20DMA`, `50DMA`, `200DMA` 키가 존재하는지 assert |
| 필수 | `positive_reasons` round-trip | `determine_market_regime()` 출력 → `fallback_render_daily_packet()` 입력 시 "없음"이 아닌 텍스트 출력 확인 |
| 필수 | 이벤트 날짜 필터링 | 미래 날짜 이벤트의 `fomc_minutes_today` flag가 오늘 출력에 포함되지 않는지 확인 |
| 권장 | `main.py` smoke test | 전체 파이프라인을 mock 데이터로 실행하고 모든 단계가 OK 반환하는지 통합 확인 |
| 권장 | `packet_builder` Section 7 | 오늘 날짜 섹션만 추출되고 타 날짜 섹션 미포함 확인 |
| 권장 | Telegram sender | API 토큰이 에러 메시지, 로그, 예외 스트링에 포함되지 않는지 assert |

---

## 수정 계획

아래 순서로 진행을 권장한다. 각 단계는 독립적으로 테스트 가능하며, 이전 단계 완료 후 다음 단계를 진행한다.

### Phase A — 핵심 데이터 파이프라인 수정 (운영 정확도에 직결)

1. `src/fetch_prices.py`: 반환 직전에 `list[dict]` → `pd.DataFrame` 변환 추가 (또는 `indicators.py` 수용 형식 확장)
2. `src/main.py` `fallback_calculate_indicators()`: 출력 필드명을 `20DMA`, `50DMA`, `200DMA`로 통일
3. `src/main.py` `fallback_render_daily_packet()`: `positive_evidence` → `positive_reasons` 키 수정
4. 테스트: `pytest tests/` 실행 후 indicators/market_regime 테스트 통과 확인

### Phase B — 이벤트 날짜 필터링 수정 (오경보 제거)

5. `src/market_regime.py` `_collect_event_flags()`: 이벤트 날짜(today, next 24h) 기반 필터 추가
6. `src/risk_engine.py` `_normalize_events()`: 동일 날짜 필터 적용
7. `events_merged.json` 직접 편집: 현재 잘못 설정된 per-event `risk_flags` 정리
8. 테스트: H4 관련 테스트 케이스 신규 작성 후 통과 확인

### Phase C — Daily Packet 가독성 수정

9. `src/main.py` `fallback_render_daily_packet()`: Section 7에 날짜 필터링 적용 (`_extract_dated_markdown_section` 호출)
10. 실행 후 `output/daily_packet.md` 수동 검토

### Phase D — 운영 환경 완성

11. `.env`에 Alpha Vantage, FMP API 키 입력 (BLS endpoint 재확인)
12. `run_pre_market.bat` 생성 (`run_post_close.bat` 복사 후 `--session pre_market` 변경)
13. `MOCK_MODE` 기본값 `"false"` 변경 및 문서화
14. Telegram 요약 Do-Not-Do 전체 7개 전달 확인

### Phase E — 테스트 보강

15. Phase A~B의 수정 내용에 대한 회귀 테스트 추가
16. `fetch_prices → indicators` 형식 계약 통합 테스트
17. 파이프라인 smoke test (`src/main.py` mock 실행)
