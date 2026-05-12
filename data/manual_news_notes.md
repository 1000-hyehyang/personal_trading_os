# Manual News Notes

이 파일은 Personal Trading OS MVP의 수동 뉴스 입력 파일이다.

MVP에서는 뉴스 자동 수집을 하지 않는다.
사용자는 SAVE, TradingView 개별 티커 뉴스, TradingView News Flow, 기업 IR, 공식 발표, 주요 언론, 직접 확인한 자료를 보고 중요한 뉴스만 여기에 수동으로 기록한다.

---

## 입력 원칙

1. 확인한 뉴스만 적는다.
2. 출처가 불분명한 내용은 `루머/미확인`으로 표시한다.
3. 뉴스 하나만 보고 매매 판단하지 않는다.
4. 가격 움직임과 뉴스의 인과관계를 단정하지 않는다.
5. 어닝, CPI, FOMC, 고용지표 전후에는 과대 진입을 피한다.
6. D급 종목의 악재성 뉴스 후 물타기 금지.
7. 장초반 갭상승 뉴스 추격 금지.

---

## 작성 형식

아래 형식을 복사해서 날짜별로 추가한다.

## YYYY-MM-DD

### Market / Macro

- [ ] SPY / QQQ:
  - Summary:
  - Source:
  - Confidence: confirmed / needs_check / rumor
  - Trading Impact:
  - Action Needed:

- [ ] VIX / Rates:
  - Summary:
  - Source:
  - Confidence: confirmed / needs_check / rumor
  - Trading Impact:
  - Action Needed:

### Semiconductors

- [ ] Ticker:
  - Summary:
  - Source:
  - Confidence: confirmed / needs_check / rumor
  - Trading Impact:
  - Action Needed:

### Mega Cap Tech

- [ ] Ticker:
  - Summary:
  - Source:
  - Confidence: confirmed / needs_check / rumor
  - Trading Impact:
  - Action Needed:

### High Beta / Speculative

- [ ] Ticker:
  - Summary:
  - Source:
  - Confidence: confirmed / needs_check / rumor
  - Trading Impact:
  - Action Needed:

---

## 2026-05-12

### Market / Macro

- [ ] SPY / QQQ:
  - Summary: 오늘 시장 방향성은 Daily Packet의 Market Regime과 이벤트 리스크를 먼저 확인.
  - Source: Personal Trading OS Daily Packet
  - Confidence: needs_check
  - Trading Impact: 시장 모드가 Caution 또는 Defensive이면 신규 공격 매매 제한.
  - Action Needed: SAVE/TradingView에서 지수 뉴스와 VIX 흐름 수동 확인.

- [ ] VIX / Rates:
  - Summary: VIX 상승 여부와 10년물 금리 움직임 확인 필요.
  - Source: TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: VIX 급등 시 고베타 종목 사이즈 확대 금지.
  - Action Needed: ^VIX, ^TNX, TLT, HYG 확인.

### Semiconductors

- [ ] NVDA:
  - Summary: 어닝 또는 AI 반도체 관련 주요 뉴스가 있는지 확인 필요.
  - Source: SAVE / TradingView / 기업 IR 수동 확인
  - Confidence: needs_check
  - Trading Impact: 어닝 7일 이내이면 스윙 진입 사이즈 축소.
  - Action Needed: 실적 날짜, 가이던스 관련 뉴스, SMH/SOXX 동조 여부 확인.

- [ ] AMD:
  - Summary: NVDA, SMH, SOXX 흐름과 동조 여부 확인.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 반도체 섹터 강세가 확인되지 않으면 단독 추격 금지.
  - Action Needed: 상대강도와 거래량 확인.

- [ ] AVGO:
  - Summary: AI 네트워킹/커스텀 실리콘 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 대형 반도체 흐름의 질 확인용.
  - Action Needed: NVDA, SMH, SOXX와 비교.

- [ ] MU / WDC / SNDK:
  - Summary: 메모리 리레이팅 또는 스토리지 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 급등 후 추격 진입 주의.
  - Action Needed: 거래량, 갭상승 여부, 섹터 확산 여부 확인.

### Mega Cap Tech

- [ ] MSFT:
  - Summary: AI/Cloud 관련 뉴스 또는 대형 기술주 수급 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: QQQ 방향성과 함께 확인.
  - Action Needed: 20DMA/50DMA 위치와 상대강도 확인.

- [ ] AAPL:
  - Summary: 제품, 중국 수요, AI 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 대형 기술주 방어력 확인용.
  - Action Needed: QQQ 대비 상대강도 확인.

- [ ] AMZN:
  - Summary: AWS, 소비, AI 인프라 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: XLY와 QQQ 동조 확인.
  - Action Needed: 섹터 강도와 거래량 확인.

- [ ] META:
  - Summary: 광고, AI, capex 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 대형 기술주 리스크 선호 확인용.
  - Action Needed: QQQ 대비 상대강도 확인.

- [ ] GOOGL:
  - Summary: AI 검색, Cloud, 규제 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 뉴스성 급등락 시 단정 금지.
  - Action Needed: 차트와 섹터 흐름 확인.

- [ ] NFLX:
  - Summary: 구독자, 광고 요금제, 콘텐츠 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: XLC 및 QQQ 흐름과 함께 확인.
  - Action Needed: 갭상승 추격 여부 확인.

- [ ] TSLA:
  - Summary: EV, 로보택시, 실적/가이던스, 정책 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 고베타 종목이므로 Caution/Defensive 모드에서 신규 공격 매매 금지.
  - Action Needed: D급 여부, VIX 상승 여부 확인.

### High Beta / Speculative

- [ ] PLTR:
  - Summary: AI 소프트웨어, 정부/상업 계약 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 급등 뉴스 추격 금지.
  - Action Needed: 거래량과 20DMA 이격 확인.

- [ ] COIN:
  - Summary: crypto 가격, 규제, 거래량 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: BTC/crypto 변동성과 동조 확인.
  - Action Needed: 고베타 리스크 확인.

- [ ] SNOW / CRWD / NET / DDOG / MDB:
  - Summary: 소프트웨어 성장주 관련 실적, 가이던스, AI 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 금리 상승 또는 QQQ 약세 시 변동성 확대 가능.
  - Action Needed: 개별 뉴스보다 섹터 흐름과 상대강도 우선 확인.

- [ ] SHOP / UBER / RBLX:
  - Summary: 고베타 성장주 뉴스 확인 필요.
  - Source: SAVE / TradingView 수동 확인
  - Confidence: needs_check
  - Trading Impact: 시장 모드가 Neutral 이하이면 신규 공격 매매 제한.
  - Action Needed: 50DMA 위/아래 여부와 거래량 확인.

- [ ] RKLB:
  - Summary: 발사 일정, 수주, 실적 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView / 기업 발표 수동 확인
  - Confidence: needs_check
  - Trading Impact: 투기성 종목으로 시장 모드가 약하면 과대 진입 금지.
  - Action Needed: 공식 발표와 루머 분리.

- [ ] ASTS:
  - Summary: 위성 발사 일정, 통신사 파트너십, 자금 조달 관련 뉴스 확인 필요.
  - Source: SAVE / TradingView / 기업 발표 수동 확인
  - Confidence: needs_check
  - Trading Impact: 루머 기반 급등락 추격 금지.
  - Action Needed: 공식 확인 여부, 일정 현실성, 차트 추세 확인.

---

## 미확인 / 루머 기록 구역

아래 구역은 매매 근거로 직접 사용하지 않는다.
GPT/Claude에 전달할 때도 `루머/미확인`으로 명확히 표시한다.

### Rumor / Unconfirmed Note Template

- Date:
- Ticker:
- Rumor / Unconfirmed Claim:
- Where Seen:
- Why It Matters:
- Verification Needed:
- Do Not Use As:

---

## 오늘의 수동 확인 체크리스트

- [ ] Daily Packet의 Market Regime 확인
- [ ] Event Overlay가 Caution인지 확인
- [ ] VIX 상승 여부 확인
- [ ] CPI/FOMC/고용/대형 어닝 일정 확인
- [ ] A급/B급/D급 종목 확인
- [ ] D급 종목 물타기 금지 확인
- [ ] 장초반 갭상승 추격 금지 확인
- [ ] SAVE/TradingView 뉴스 수동 확인
- [ ] 뉴스와 가격 움직임의 인과관계 단정 금지
- [ ] 손절가 없는 진입 금지