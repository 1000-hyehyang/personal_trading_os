# Personal Trading OS MVP — 01_RUNBOOK_WINDOWS.md

**문서명:** Personal Trading OS MVP — Windows Runbook  
**문서 버전:** v1.0  
**작성 기준일:** 2026-05-12  
**기준 문서:** `00_PROJECT_SPEC.md`  
**대상 환경:** Windows 10 / Windows 11, Python 3.12, PowerShell  
**프로젝트 경로:** `C:\trading\personal_trading_os`

---

## 1. 운영 목표

`Personal Trading OS MVP`는 Windows에서 매일 자동 실행되어 다음 작업을 수행한다.

1. 미국장 가격 데이터 수집
2. 기술 지표 계산
3. 어닝 및 경제 이벤트 수집
4. 수동 이벤트 및 뉴스 메모 병합
5. 시장 모드 판정
6. 관심종목 A/B/C/D 랭킹
7. Breakout / Pullback / Avoid 후보 분류
8. 리스크 경고 및 금지 행동 생성
9. Daily Packet 및 GPT/Claude용 프롬프트 생성
10. Telegram으로 요약과 파일 전송

자동 실행 흐름은 다음과 같다.

```text
Windows Task Scheduler
  ↓
run_post_close.bat
  ↓
.venv\Scripts\python.exe src\main.py --session post_close
  ↓
Daily Packet / Prompt / Telegram 전송
```

MVP는 자동매매, 주문 API, 브로커 API, TradingView scraping, OpenAI API, Claude API를 사용하지 않는다. 사용자의 최종 매수·매도 판단을 대체하지 않는다.

---

## 2. 기준 환경

```text
OS: Windows 10 또는 Windows 11
Shell: PowerShell
Python: 3.12
Project Path: C:\trading\personal_trading_os
Virtual Env: C:\trading\personal_trading_os\.venv
Scheduler: Windows Task Scheduler
Telegram: BotFather로 생성한 Telegram Bot
```

프로젝트 경로는 반드시 아래 경로를 기준으로 한다.

```text
C:\trading\personal_trading_os
```

다음 경로는 피한다.

```text
C:\Users\사용자명\바탕 화면\미국 주식 프로그램
C:\Users\사용자명\OneDrive\문서\트레이딩 프로그램
```

한글, 공백, OneDrive 동기화 경로는 Task Scheduler 실행, 로그 저장, 파일 경로 처리에서 문제를 만들 수 있으므로 사용하지 않는다.

---

## 3. PowerShell 기본 준비

PowerShell을 실행한 뒤 아래 명령으로 Python 3.12가 설치되어 있는지 확인한다.

```powershell
py -0p
py -3.12 --version
```

정상 예시는 다음과 같다.

```text
Python 3.12.x
```

`py -3.12`가 동작하지 않으면 Python 3.12가 설치되어 있지 않거나 Python Launcher가 등록되지 않은 상태다. 이 경우 Python 3.12를 설치한 뒤 다시 확인한다.

---

## 4. 프로젝트 폴더 준비

프로젝트 루트 폴더가 없으면 생성한다.

```powershell
New-Item -ItemType Directory -Force -Path C:\trading\personal_trading_os
Set-Location C:\trading\personal_trading_os
```

필수 폴더를 생성한다.

```powershell
New-Item -ItemType Directory -Force -Path .\config
New-Item -ItemType Directory -Force -Path .\data
New-Item -ItemType Directory -Force -Path .\output
New-Item -ItemType Directory -Force -Path .\cache
New-Item -ItemType Directory -Force -Path .\logs
New-Item -ItemType Directory -Force -Path .\src
New-Item -ItemType Directory -Force -Path .\tests
New-Item -ItemType Directory -Force -Path .\docs
```

폴더 구조를 확인한다.

```powershell
Get-ChildItem C:\trading\personal_trading_os
```

기준 구조는 다음과 같다.

```text
C:\trading\personal_trading_os\
  config\
  data\
  output\
  cache\
  logs\
  src\
  tests\
  docs\
  run_post_close.bat
  run_pre_market.bat
  .env
  .env.example
  .gitignore
  requirements.txt
  README.md
```

---

## 5. Python 3.12 가상환경 생성

프로젝트 루트로 이동한다.

```powershell
Set-Location C:\trading\personal_trading_os
```

`.venv` 가상환경을 생성한다.

```powershell
py -3.12 -m venv .venv
```

가상환경의 Python 실행 파일을 확인한다.

```powershell
.\.venv\Scripts\python.exe --version
```

정상 예시는 다음과 같다.

```text
Python 3.12.x
```

이 프로젝트는 자동 실행에서 `activate`를 사용하지 않는다. 항상 아래처럼 `.venv\Scripts\python.exe`를 직접 호출한다.

```powershell
.\.venv\Scripts\python.exe src\main.py --session post_close
```

---

## 6. requirements.txt 작성 및 설치

`requirements.txt`가 없다면 아래 명령으로 생성한다.

```powershell
@'
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
'@ | Set-Content -Path .\requirements.txt -Encoding UTF8
```

pip을 업그레이드한다.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

패키지를 설치한다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

설치 확인 예시:

```powershell
.\.venv\Scripts\python.exe -m pip list
```

필수 패키지 import 테스트:

```powershell
.\.venv\Scripts\python.exe -c "import pandas, numpy, yfinance, yaml, dotenv, requests; print('OK')"
```

정상 출력:

```text
OK
```

---

## 7. .env 설정

민감정보는 `.env`에만 저장한다. GitHub, Claude, ChatGPT, 문서 본문, 로그에 실제 토큰과 API Key를 노출하지 않는다.

`.env.example`을 먼저 생성한다.

```powershell
@'
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
FMP_API_KEY=optional_fmp_key
DATA_PROVIDER=yfinance
EVENT_PROVIDER=alpha_vantage_fmp_bls_fed
'@ | Set-Content -Path .\.env.example -Encoding UTF8
```

`.env.example`을 복사해 실제 `.env`를 만든다.

```powershell
Copy-Item .\.env.example .\.env -Force
notepad .\.env
```

`.env`는 다음 형식으로 작성한다.

```env
TELEGRAM_BOT_TOKEN=1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
ALPHAVANTAGE_API_KEY=xxxxxxxxxxxxxxxx
FMP_API_KEY=
DATA_PROVIDER=yfinance
EVENT_PROVIDER=alpha_vantage_fmp_bls_fed
```

FMP API Key는 optional이다. FMP를 사용하지 않으면 아래처럼 비워둔다.

```env
FMP_API_KEY=
```

`.env` 키가 채워졌는지 값 노출 없이 확인한다.

```powershell
Get-Content .\.env | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') {
        if ($matches.value.Length -gt 0) {
            "$($matches.key)=<set>"
        } else {
            "$($matches.key)=<empty>"
        }
    }
}
```

---

## 8. .gitignore 작성

민감정보와 실행 산출물을 Git에 올리지 않도록 `.gitignore`를 작성한다.

```powershell
@'
.env
.venv/
__pycache__/
*.pyc
logs/
cache/
output/
.pytest_cache/
'@ | Set-Content -Path .\.gitignore -Encoding UTF8
```

확인:

```powershell
Get-Content .\.gitignore
```

---

## 9. Telegram BotFather 설정

Telegram 전송은 BotFather로 생성한 Bot Token과 Chat ID를 사용한다.

### 9.1 Bot 생성

Telegram 앱에서 다음 순서로 진행한다.

1. Telegram에서 `@BotFather` 검색
2. `@BotFather`와 대화 시작
3. `/newbot` 입력
4. Bot 표시 이름 입력  
   예: `Personal Trading OS`
5. Bot username 입력  
   예: `personal_trading_os_bot`  
   username은 보통 `bot`으로 끝나야 한다.
6. BotFather가 발급한 Bot Token을 복사한다.

`.env`에 입력한다.

```env
TELEGRAM_BOT_TOKEN=발급받은_Bot_Token
```

### 9.2 Bot에 최초 메시지 보내기

생성한 Bot을 Telegram에서 검색해 대화를 시작한다.

```text
/start
```

개인 채팅으로 받을 경우 사용자가 먼저 Bot에게 메시지를 보내야 `getUpdates`에서 Chat ID를 확인할 수 있다.

### 9.3 Chat ID 확인

PowerShell에서 `.env`의 Bot Token을 읽는다.

```powershell
Set-Location C:\trading\personal_trading_os

$token = (Get-Content .\.env | Where-Object { $_ -match '^TELEGRAM_BOT_TOKEN=' }) -replace '^TELEGRAM_BOT_TOKEN=', ''
```

`getUpdates`를 호출한다.

```powershell
Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getUpdates" | ConvertTo-Json -Depth 10
```

출력에서 아래 항목을 찾는다.

```json
"chat": {
  "id": 123456789
}
```

`.env`에 입력한다.

```env
TELEGRAM_CHAT_ID=123456789
```

그룹 채팅으로 받을 경우 Bot을 그룹에 초대한 뒤 그룹에서 메시지를 보내고 `getUpdates`를 다시 확인한다. 그룹 Chat ID는 보통 음수 값이다.

```env
TELEGRAM_CHAT_ID=-123456789
```

### 9.4 Telegram 전송 테스트

`.env`에서 Token과 Chat ID를 읽는다.

```powershell
$envLines = Get-Content .\.env
$token = ($envLines | Where-Object { $_ -match '^TELEGRAM_BOT_TOKEN=' }) -replace '^TELEGRAM_BOT_TOKEN=', ''
$chatId = ($envLines | Where-Object { $_ -match '^TELEGRAM_CHAT_ID=' }) -replace '^TELEGRAM_CHAT_ID=', ''
```

테스트 메시지를 보낸다.

```powershell
Invoke-RestMethod `
  -Uri "https://api.telegram.org/bot$token/sendMessage" `
  -Method Post `
  -Body @{
    chat_id = $chatId
    text = "Personal Trading OS Telegram test"
  }
```

Telegram에 테스트 메시지가 도착하면 Bot Token과 Chat ID 설정은 정상이다.

---

## 10. Alpha Vantage API Key 설정

Alpha Vantage는 MVP의 1차 어닝 데이터 소스다. 프로젝트 스펙 기준으로 `EARNINGS_CALENDAR`를 사용해 향후 어닝 캘린더를 수집하고, watchlist 종목만 필터링해 이벤트 리스크에 반영한다.

### 10.1 API Key 발급

1. Alpha Vantage API Key 발급 페이지에서 이메일 등 필요한 정보를 입력한다.
2. 발급된 API Key를 복사한다.
3. `.env`에 입력한다.

```env
ALPHAVANTAGE_API_KEY=발급받은_Alpha_Vantage_Key
```

### 10.2 Alpha Vantage Key 테스트

PowerShell에서 `.env`의 Key를 읽는다.

```powershell
Set-Location C:\trading\personal_trading_os

$alphaKey = (Get-Content .\.env | Where-Object { $_ -match '^ALPHAVANTAGE_API_KEY=' }) -replace '^ALPHAVANTAGE_API_KEY=', ''
```

`EARNINGS_CALENDAR`를 테스트한다.

```powershell
$url = "https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=$alphaKey"
Invoke-WebRequest -Uri $url -OutFile "$env:TEMP\alpha_earnings_calendar.csv"
Get-Content "$env:TEMP\alpha_earnings_calendar.csv" -TotalCount 5
```

정상이라면 CSV 헤더와 데이터 일부가 출력된다.

예상 형태:

```text
symbol,name,reportDate,fiscalDateEnding,estimate,currency
...
```

---

## 11. FMP API Key 설정 — Optional

FMP는 경제 이벤트 캘린더용 optional 데이터 소스다. 프로젝트 스펙에서는 경제 이벤트 수집 순서를 FMP Economic Calendar, BLS Calendar, Fed FOMC Calendar, `events_manual.yaml` 순서로 둔다.

FMP를 사용할 경우 `.env`에 Key를 입력한다.

```env
FMP_API_KEY=발급받은_FMP_Key
```

FMP를 사용하지 않을 경우 비워둔다.

```env
FMP_API_KEY=
```

FMP Key 테스트:

```powershell
$fmpKey = (Get-Content .\.env | Where-Object { $_ -match '^FMP_API_KEY=' }) -replace '^FMP_API_KEY=', ''

if ($fmpKey.Length -gt 0) {
    Invoke-RestMethod -Uri "https://financialmodelingprep.com/stable/economic-calendar?apikey=$fmpKey" |
        Select-Object -First 3
} else {
    Write-Host "FMP_API_KEY is empty. Skipping FMP test."
}
```

FMP는 optional이므로 Key가 없더라도 MVP는 BLS, Fed, manual event fallback을 사용할 수 있도록 구현하는 것이 좋다.

---

## 12. 설정 파일 사전 확인

실행 전에 주요 설정 파일이 있는지 확인한다.

```powershell
Set-Location C:\trading\personal_trading_os

Test-Path .\config\watchlist.yaml
Test-Path .\config\settings.yaml
Test-Path .\config\rules.yaml
Test-Path .\config\setups.yaml
Test-Path .\config\events_manual.yaml
Test-Path .\data\manual_news_notes.md
```

모두 `True`가 나와야 한다.

없으면 최소한 빈 파일이라도 생성한다.

```powershell
New-Item -ItemType File -Force -Path .\data\manual_news_notes.md
```

`manual_news_notes.md`는 뉴스 자동 수집 대신 사용자가 SAVE, TradingView, 직접 확인한 뉴스를 수동 입력하는 파일이다. MVP에서는 뉴스 자동 수집을 하지 않는다.

---

## 13. run_post_close.bat 작성

`run_post_close.bat`는 Task Scheduler가 호출하는 실제 실행 파일이다.

PowerShell에서 프로젝트 루트로 이동한다.

```powershell
Set-Location C:\trading\personal_trading_os
```

아래 내용으로 `run_post_close.bat`를 생성한다.

```powershell
@'
@echo off
setlocal

cd /d C:\trading\personal_trading_os

if not exist logs mkdir logs
if not exist output mkdir output
if not exist cache mkdir cache

chcp 65001 >nul
set PYTHONUTF8=1

echo [%date% %time%] Starting post-close run >> logs\post_close.log

if not exist .venv\Scripts\python.exe (
    echo [%date% %time%] ERROR: .venv\Scripts\python.exe not found >> logs\post_close.log
    echo [%date% %time%] Please create venv with: py -3.12 -m venv .venv >> logs\post_close.log
    exit /b 1
)

if not exist src\main.py (
    echo [%date% %time%] ERROR: src\main.py not found >> logs\post_close.log
    exit /b 1
)

.venv\Scripts\python.exe src\main.py --session post_close >> logs\post_close.log 2>&1

set EXIT_CODE=%ERRORLEVEL%

echo [%date% %time%] Finished post-close run with exit code %EXIT_CODE% >> logs\post_close.log

exit /b %EXIT_CODE%
'@ | Set-Content -Path .\run_post_close.bat -Encoding ASCII
```

내용 확인:

```powershell
Get-Content .\run_post_close.bat
```

---

## 14. 수동 실행 테스트

### 14.1 Python 직접 실행 테스트

먼저 Task Scheduler 없이 Python을 직접 실행한다.

```powershell
Set-Location C:\trading\personal_trading_os
.\.venv\Scripts\python.exe src\main.py --session post_close
```

정상 실행 후 출력 파일을 확인한다.

```powershell
Get-ChildItem .\output
```

필수 산출물은 다음과 같다.

```text
output\daily_packet.md
output\daily_packet.json
output\prompt_for_gpt.txt
output\prompt_for_claude.txt
output\telegram_summary.txt
output\events_auto.json
output\events_merged.json
```

### 14.2 BAT 실행 테스트

이제 `run_post_close.bat`를 수동 실행한다.

```powershell
Set-Location C:\trading\personal_trading_os
.\run_post_close.bat
```

종료 코드를 확인한다.

```powershell
$LASTEXITCODE
```

정상 종료는 보통 다음과 같다.

```text
0
```

로그를 확인한다.

```powershell
Get-Content .\logs\post_close.log -Tail 100
```

### 14.3 결과 파일 확인

```powershell
Test-Path .\output\daily_packet.md
Test-Path .\output\daily_packet.json
Test-Path .\output\prompt_for_gpt.txt
Test-Path .\output\prompt_for_claude.txt
Test-Path .\output\telegram_summary.txt
Test-Path .\output\events_auto.json
Test-Path .\output\events_merged.json
```

모두 `True`가 나오면 기본 산출물 생성은 정상이다.

### 14.4 Telegram 수신 확인

Telegram에서 다음이 도착했는지 확인한다.

```text
1. 요약 메시지
2. daily_packet.md
3. prompt_for_gpt.txt
4. prompt_for_claude.txt
```

---

## 15. Windows Task Scheduler 등록

Post-close 리포트는 한국 시간 기준 화~토 오전 06:50에 실행한다. Windows Task Scheduler는 PC의 로컬 시간을 사용하므로 Windows 시간대가 한국 시간이 아니라면 실행 시간을 조정해야 한다.

PowerShell에서 아래 명령을 실행한다.

```powershell
schtasks /Create /TN "PersonalTradingOS_PostClose" /TR "C:\trading\personal_trading_os\run_post_close.bat" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 06:50 /F
```

등록 확인:

```powershell
schtasks /Query /TN "PersonalTradingOS_PostClose" /V /FO LIST
```

즉시 수동 실행:

```powershell
schtasks /Run /TN "PersonalTradingOS_PostClose"
```

실행 후 로그 확인:

```powershell
Get-Content C:\trading\personal_trading_os\logs\post_close.log -Tail 100
```

스케줄 삭제가 필요할 때:

```powershell
schtasks /Delete /TN "PersonalTradingOS_PostClose" /F
```

---

## 16. 로그 확인 방법

### 16.1 최근 로그 확인

```powershell
Get-Content C:\trading\personal_trading_os\logs\post_close.log -Tail 100
```

### 16.2 전체 로그 확인

```powershell
notepad C:\trading\personal_trading_os\logs\post_close.log
```

### 16.3 에러만 검색

```powershell
Select-String -Path C:\trading\personal_trading_os\logs\post_close.log -Pattern "ERROR","Exception","Traceback","failed","Failed"
```

### 16.4 오늘 실행 흔적 확인

```powershell
Select-String -Path C:\trading\personal_trading_os\logs\post_close.log -Pattern "Starting post-close run","Finished post-close run"
```

### 16.5 Task Scheduler 이벤트 확인

```powershell
Get-WinEvent -LogName Microsoft-Windows-TaskScheduler/Operational -MaxEvents 50 |
    Where-Object { $_.Message -like "*PersonalTradingOS_PostClose*" } |
    Select-Object TimeCreated, Id, Message
```

---

## 17. 운영 루틴

### 17.1 매일 확인할 것

1. Telegram 메시지가 도착했는지 확인한다.
2. `daily_packet.md`를 연다.
3. `A Grade`, `B Grade`, `D Grade`, `Avoid` 항목을 확인한다.
4. `Risk Warnings`와 `Today's Do-Not-Do List`를 확인한다.
5. SAVE / TradingView에서 주요 뉴스와 차트를 수동 확인한다.
6. 필요 시 `data\manual_news_notes.md`를 업데이트한다.
7. `prompt_for_gpt.txt`를 ChatGPT Pro에 붙여넣어 트레이딩 플랜을 생성한다.
8. `prompt_for_claude.txt`를 Claude Max에 붙여넣어 리스크 리뷰를 받는다.
9. 최종 매매 판단은 사용자가 직접 한다.

### 17.2 수동 뉴스 메모 업데이트

```powershell
notepad C:\trading\personal_trading_os\data\manual_news_notes.md
```

예시:

```markdown
# Manual News Notes

## 2026-05-12

- NVDA: TradingView 뉴스에서 실적 관련 변동성 확대 가능성 확인
- TSLA: SAVE에서 특정 뉴스 확인 필요
- QQQ: 장마감 후 대형 기술주 흐름 확인 필요
```

수동 뉴스 메모는 자동 뉴스 수집을 대체하는 운영 입력이다.

---

## 18. 자주 나는 오류와 해결법

### 18.1 `py -3.12`가 인식되지 않음

증상:

```text
py : The term 'py' is not recognized
```

확인:

```powershell
python --version
where python
```

해결:

1. Python 3.12 설치
2. 설치 시 `Add python.exe to PATH` 선택
3. PowerShell 재시작
4. 다시 확인

```powershell
py -0p
py -3.12 --version
```

---

### 18.2 `.venv\Scripts\python.exe`가 없음

증상:

```text
ERROR: .venv\Scripts\python.exe not found
```

원인:

1. 가상환경을 만들지 않음
2. 다른 폴더에서 가상환경을 만듦
3. 프로젝트 경로가 다름

해결:

```powershell
Set-Location C:\trading\personal_trading_os
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe --version
```

---

### 18.3 `ModuleNotFoundError`

증상:

```text
ModuleNotFoundError: No module named 'pandas'
ModuleNotFoundError: No module named 'yfinance'
ModuleNotFoundError: No module named 'dotenv'
```

원인:

1. requirements 설치 누락
2. 시스템 Python으로 실행함
3. `.venv`가 아닌 다른 Python으로 실행함

해결:

```powershell
Set-Location C:\trading\personal_trading_os
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

확인:

```powershell
.\.venv\Scripts\python.exe -c "import pandas, yfinance, dotenv; print('OK')"
```

---

### 18.4 `requirements.txt not found`

증상:

```text
ERROR: Could not open requirements file
```

원인:

현재 위치가 프로젝트 루트가 아님.

해결:

```powershell
Set-Location C:\trading\personal_trading_os
Test-Path .\requirements.txt
```

없으면 다시 생성한다.

```powershell
@'
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
'@ | Set-Content -Path .\requirements.txt -Encoding UTF8
```

---

### 18.5 PowerShell Execution Policy 오류

증상:

```text
running scripts is disabled on this system
```

원인:

`activate.ps1`을 실행하려고 했기 때문일 가능성이 높다.

해결:

이 프로젝트에서는 activate를 사용하지 않는다. 아래처럼 직접 호출한다.

```powershell
.\.venv\Scripts\python.exe src\main.py --session post_close
```

Task Scheduler에서도 동일하게 `.venv\Scripts\python.exe`를 직접 호출한다.

---

### 18.6 `.env` 값이 로드되지 않음

증상:

```text
TELEGRAM_BOT_TOKEN is missing
ALPHAVANTAGE_API_KEY is missing
```

확인:

```powershell
Get-ChildItem -Force C:\trading\personal_trading_os | Where-Object { $_.Name -like ".env*" }
```

흔한 원인:

1. 파일명이 `.env.txt`임
2. `.env`가 프로젝트 루트가 아닌 다른 폴더에 있음
3. 키 이름 오타
4. 값 앞뒤에 불필요한 공백이 있음

정상 키 이름:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ALPHAVANTAGE_API_KEY=
FMP_API_KEY=
DATA_PROVIDER=yfinance
EVENT_PROVIDER=alpha_vantage_fmp_bls_fed
```

해결:

```powershell
notepad C:\trading\personal_trading_os\.env
```

---

### 18.7 Telegram `401 Unauthorized`

증상:

```text
Unauthorized
```

원인:

1. Bot Token이 틀림
2. Token 앞뒤에 공백이 있음
3. BotFather에서 Token을 재발급했는데 `.env`를 업데이트하지 않음

해결:

1. BotFather에서 Token 확인 또는 재발급
2. `.env`의 `TELEGRAM_BOT_TOKEN` 수정
3. 다시 테스트

```powershell
$token = (Get-Content .\.env | Where-Object { $_ -match '^TELEGRAM_BOT_TOKEN=' }) -replace '^TELEGRAM_BOT_TOKEN=', ''
Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getMe"
```

---

### 18.8 Telegram `400 Bad Request: chat not found`

증상:

```text
Bad Request: chat not found
```

원인:

1. `TELEGRAM_CHAT_ID`가 틀림
2. 사용자가 Bot에게 `/start`를 보내지 않음
3. 그룹방에서 Bot 권한이 부족함
4. 그룹 Chat ID 대신 개인 Chat ID를 사용함

해결:

1. Bot에게 `/start` 보내기
2. `getUpdates`로 Chat ID 재확인
3. `.env` 수정

```powershell
$token = (Get-Content .\.env | Where-Object { $_ -match '^TELEGRAM_BOT_TOKEN=' }) -replace '^TELEGRAM_BOT_TOKEN=', ''
Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getUpdates" | ConvertTo-Json -Depth 10
```

---

### 18.9 Alpha Vantage 응답이 비정상

증상:

```text
Invalid API call
Thank you for using Alpha Vantage
rate limit
demo
```

원인:

1. `ALPHAVANTAGE_API_KEY`가 비어 있음
2. demo key를 그대로 사용함
3. 호출 제한에 걸림
4. API URL 파라미터가 잘못됨

해결:

```powershell
$alphaKey = (Get-Content .\.env | Where-Object { $_ -match '^ALPHAVANTAGE_API_KEY=' }) -replace '^ALPHAVANTAGE_API_KEY=', ''
$url = "https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=$alphaKey"
Invoke-WebRequest -Uri $url -OutFile "$env:TEMP\alpha_test.csv"
Get-Content "$env:TEMP\alpha_test.csv" -TotalCount 10
```

호출 제한이 의심되면 캐시를 사용하거나 재시도 간격을 늘린다.

---

### 18.10 FMP 오류

증상:

```text
401 Unauthorized
403 Forbidden
429 Too Many Requests
```

원인:

1. FMP Key가 없음
2. 무료 플랜 제한
3. 호출 제한
4. endpoint 권한 없음

해결:

FMP는 optional이므로 `.env`에서 비워둘 수 있다.

```env
FMP_API_KEY=
```

코드는 FMP 실패 시 BLS, Fed, `events_manual.yaml` 쪽으로 fallback하도록 구현하는 것이 좋다.

---

### 18.11 yfinance 데이터 오류

증상:

```text
JSONDecodeError
No data found
possibly delisted
```

원인:

1. 네트워크 문제
2. Yahoo Finance 응답 지연
3. ticker 오타
4. 특수 ticker 표기 문제  
   예: `^VIX`, `^TNX`

해결:

1. 인터넷 연결 확인
2. 잠시 후 재실행
3. ticker 목록 확인

```powershell
notepad C:\trading\personal_trading_os\config\watchlist.yaml
```

4. 캐시가 손상된 경우 캐시 삭제 후 재실행

```powershell
Remove-Item C:\trading\personal_trading_os\cache\prices_cache.json -ErrorAction SilentlyContinue
.\run_post_close.bat
```

---

### 18.12 Task Scheduler는 실행됐는데 결과 파일이 없음

증상:

```text
Task Scheduler에서는 실행 성공처럼 보이지만 output 파일이 없음
```

확인:

```powershell
Get-Content C:\trading\personal_trading_os\logs\post_close.log -Tail 200
```

흔한 원인:

1. batch 파일의 working directory 문제
2. `.venv` 없음
3. `.env` 없음
4. `src\main.py` 없음
5. 권한 문제

해결:

`run_post_close.bat`에 아래 줄이 있는지 확인한다.

```bat
cd /d C:\trading\personal_trading_os
```

그리고 수동 실행이 정상인지 먼저 확인한다.

```powershell
Set-Location C:\trading\personal_trading_os
.\run_post_close.bat
```

---

### 18.13 Task Scheduler 결과가 `0x1`

증상:

```text
Last Run Result: 0x1
```

원인:

보통 Python 실행 실패, 경로 문제, 파일 누락, API 오류다.

해결 순서:

```powershell
Get-Content C:\trading\personal_trading_os\logs\post_close.log -Tail 200
```

직접 실행한다.

```powershell
Set-Location C:\trading\personal_trading_os
.\run_post_close.bat
```

Python 직접 실행도 확인한다.

```powershell
.\.venv\Scripts\python.exe src\main.py --session post_close
```

---

### 18.14 정해진 시간에 실행되지 않음

원인:

1. PC가 꺼져 있음
2. PC가 절전 상태
3. Windows 시간대가 한국 시간이 아님
4. 작업이 비활성화됨
5. Task Scheduler 기록상 실패

확인:

```powershell
schtasks /Query /TN "PersonalTradingOS_PostClose" /V /FO LIST
```

Windows 시간대 확인:

```powershell
Get-TimeZone
```

현재 작업을 즉시 실행해본다.

```powershell
schtasks /Run /TN "PersonalTradingOS_PostClose"
```

---

### 18.15 로그 한글이 깨짐

증상:

```text
로그의 한글이 깨져 보임
```

해결:

`run_post_close.bat`에 아래 줄이 포함되어 있는지 확인한다.

```bat
chcp 65001 >nul
set PYTHONUTF8=1
```

그래도 깨지면 Python 코드에서 파일 저장 시 `encoding="utf-8"`을 명시한다.

```python
open(path, "w", encoding="utf-8")
```

---

## 19. 운영 체크리스트

### 19.1 최초 설치 체크리스트

```text
[ ] Python 3.12 설치 확인
[ ] C:\trading\personal_trading_os 폴더 생성
[ ] .venv 생성
[ ] requirements.txt 설치
[ ] .env 작성
[ ] TELEGRAM_BOT_TOKEN 입력
[ ] TELEGRAM_CHAT_ID 입력
[ ] ALPHAVANTAGE_API_KEY 입력
[ ] FMP_API_KEY optional 처리
[ ] config 파일 존재 확인
[ ] data\manual_news_notes.md 존재 확인
[ ] run_post_close.bat 작성
[ ] Python 직접 실행 성공
[ ] BAT 수동 실행 성공
[ ] output 파일 생성 확인
[ ] Telegram 수신 확인
[ ] Task Scheduler 등록
[ ] Task Scheduler 수동 실행 성공
[ ] logs\post_close.log 확인
```

### 19.2 매일 운영 체크리스트

```text
[ ] Telegram 요약 수신
[ ] daily_packet.md 확인
[ ] A/B/C/D 등급 확인
[ ] Breakout/Pullback/Avoid 확인
[ ] Risk Warnings 확인
[ ] Today's Do-Not-Do List 확인
[ ] SAVE / TradingView 뉴스 수동 확인
[ ] 필요 시 manual_news_notes.md 업데이트
[ ] prompt_for_gpt.txt를 ChatGPT Pro에 입력
[ ] prompt_for_claude.txt를 Claude Max에 입력
[ ] 최종 판단은 직접 수행
```

---

## 20. MVP 완료 기준

이 Runbook 기준으로 아래가 모두 충족되면 Windows 운영 준비가 완료된 것으로 본다.

```text
1. Windows에서 Python 3.12 가상환경이 정상 동작한다.
2. C:\trading\personal_trading_os 구조가 생성되어 있다.
3. requirements.txt 설치가 완료되어 있다.
4. .env에 Telegram, Alpha Vantage 설정이 들어 있다.
5. FMP API Key는 optional로 처리되어 있다.
6. run_post_close.bat가 정상 실행된다.
7. src\main.py --session post_close가 실행된다.
8. output\daily_packet.md가 생성된다.
9. output\daily_packet.json이 생성된다.
10. output\prompt_for_gpt.txt가 생성된다.
11. output\prompt_for_claude.txt가 생성된다.
12. output\telegram_summary.txt가 생성된다.
13. output\events_auto.json이 생성된다.
14. output\events_merged.json이 생성된다.
15. Telegram으로 요약과 파일이 전송된다.
16. Windows Task Scheduler에서 자동 실행된다.
17. logs\post_close.log에 실행 로그가 남는다.
18. logs\post_close_console.log에 BAT 래퍼 로그가 남는다.
19. logs\pre_market.log에 pre-market 실행 로그가 남는다.
20. logs\pre_market_console.log에 pre-market BAT 래퍼 로그가 남는다.
```

---

## 21. Windows Task Scheduler 최종 운영 섹션

> 기준: `00_PROJECT_SPEC.md`, `01_RUNBOOK_WINDOWS.md`, 현재 `run_post_close.bat`, `run_pre_market.bat`, `src\main.py` 구조
> 상태: `phase12-review` 브랜치 / `C:\trading\personal_trading_os` / Python 3.12 / `.venv\Scripts\python.exe` 직접 호출

---

### 21.1 기준 상태

```text
Branch: phase12-review
Project Path: C:\trading\personal_trading_os
Python: 3.12
Execution: .venv\Scripts\python.exe 직접 호출
Scheduler: Windows Task Scheduler
Shell: PowerShell 기준

MVP 제외:
- 자동매매 없음
- TradingView scraping 없음
- ChatGPT/OpenAI API 사용 없음
- Claude API 사용 없음
- 뉴스 자동 수집 없음
```

운영 파일:

```text
run_post_close.bat
run_pre_market.bat
src\main.py
logs\
output\
cache\
```

주의:

```text
.env는 절대 공유하지 않는다.
output\, logs\, cache\는 Git에 올리지 않는다.
Task Scheduler에서는 venv activate를 사용하지 않는다.
항상 .venv\Scripts\python.exe를 직접 호출한다.
```

---

### 21.2 로그 파일 역할 분리

`src\main.py`의 `setup_logging()`은 Python FileHandler와 StreamHandler를 동시에 등록한다.

```text
logs\post_close.log          Python FileHandler — Python 내부 실행 로그 (main.py 직접 기록)
logs\post_close_console.log  BAT 리디렉션 — BAT 래퍼 메시지 + Python stdout 캡처

logs\pre_market.log          Python FileHandler — Python 내부 실행 로그 (main.py 직접 기록)
logs\pre_market_console.log  BAT 리디렉션 — BAT 래퍼 메시지 + Python stdout 캡처
```

두 파일 모두 동일한 Python 로그 내용을 담지만 역할이 다르다.

- `*.log` → Python이 직접 기록. Task Scheduler 환경에서 실패해도 남는다.
- `*_console.log` → BAT가 캡처. `Starting` / `Finished` / exit code 추적에 사용한다.

---

### 21.3 schtasks 등록 명령어

#### Post-close 등록

한국 시간 기준 화~토 오전 06:50 실행.

```powershell
schtasks /Create /TN "PersonalTradingOS_PostClose" /TR "C:\trading\personal_trading_os\run_post_close.bat" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 06:50 /F
```

#### Pre-market 등록 — 미국 서머타임 기간

미국장이 한국 시간 22:30에 열리는 기간에는 21:00 KST 실행.

```powershell
schtasks /Create /TN "PersonalTradingOS_PreMarket" /TR "C:\trading\personal_trading_os\run_pre_market.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 21:00 /F
```

#### Pre-market 등록 — 미국 표준시간 기간

미국장이 한국 시간 23:30에 열리는 기간에는 22:00 KST 실행.

```powershell
schtasks /Create /TN "PersonalTradingOS_PreMarket" /TR "C:\trading\personal_trading_os\run_pre_market.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 22:00 /F
```

주의:

```text
Windows Task Scheduler는 Windows 로컬 시간을 사용한다.
미국 서머타임 전환 시 pre_market 작업 시간을 직접 조정한다.
```

---

### 21.4 등록 확인 명령어

```powershell
schtasks /Query /TN "PersonalTradingOS_PostClose" /V /FO LIST
schtasks /Query /TN "PersonalTradingOS_PreMarket" /V /FO LIST
```

확인 항목:

```text
TaskName
Next Run Time
Status
Last Run Time
Last Result
Task To Run
Schedule
```

정상적인 `Task To Run` 예시:

```text
C:\trading\personal_trading_os\run_post_close.bat
C:\trading\personal_trading_os\run_pre_market.bat
```

---

### 21.5 수동 실행 테스트 명령어

#### 1단계 — Python 직접 실행

```powershell
Set-Location C:\trading\personal_trading_os

.\.venv\Scripts\python.exe src\main.py --session post_close
.\.venv\Scripts\python.exe src\main.py --session pre_market
```

#### 2단계 — BAT 직접 실행

```powershell
Set-Location C:\trading\personal_trading_os

.\run_post_close.bat
$LASTEXITCODE

.\run_pre_market.bat
$LASTEXITCODE
```

정상 종료: `0`

#### 3단계 — Task Scheduler 즉시 실행

```powershell
schtasks /Run /TN "PersonalTradingOS_PostClose"
schtasks /Run /TN "PersonalTradingOS_PreMarket"
```

주의:

```text
schtasks /Run은 작업을 시작했다는 뜻이지, 성공 완료를 의미하지 않는다.
실제 성공 여부는 로그와 Last Result로 확인한다.
```

---

### 21.6 출력 파일 확인 명령어

```powershell
Set-Location C:\trading\personal_trading_os

Test-Path .\output\daily_packet.md
Test-Path .\output\daily_packet.json
Test-Path .\output\prompt_for_gpt.txt
Test-Path .\output\prompt_for_claude.txt
Test-Path .\output\telegram_summary.txt
Test-Path .\output\events_auto.json
Test-Path .\output\events_merged.json
```

최근 수정 시간 확인:

```powershell
Get-ChildItem .\output |
  Select-Object Name, LastWriteTime, Length |
  Sort-Object LastWriteTime -Descending
```

---

### 21.7 로그 확인 명령어

#### Post-close 로그

```powershell
Get-Content C:\trading\personal_trading_os\logs\post_close.log -Tail 200
Get-Content C:\trading\personal_trading_os\logs\post_close_console.log -Tail 200
```

#### Pre-market 로그

```powershell
Get-Content C:\trading\personal_trading_os\logs\pre_market.log -Tail 200
Get-Content C:\trading\personal_trading_os\logs\pre_market_console.log -Tail 200
```

#### 에러 검색

```powershell
Select-String -Path C:\trading\personal_trading_os\logs\*.log `
  -Pattern "ERROR","Exception","Traceback","failed","Failed","FAIL","WARN"
```

#### 실행 시작/종료 흔적 검색

```powershell
Select-String -Path C:\trading\personal_trading_os\logs\*_console.log `
  -Pattern "Starting","Finished","exit code"
```

---

### 21.8 Task Scheduler 실패 시 확인 순서

#### 1단계 — Last Result 확인

```powershell
schtasks /Query /TN "PersonalTradingOS_PostClose" /V /FO LIST
```

흔한 결과:

```text
0x0      정상
0x1      일반 실행 실패
0x2      파일/경로 문제 가능성
0x41301  작업 실행 중
```

#### 2단계 — BAT 콘솔 로그 확인

```powershell
Get-Content C:\trading\personal_trading_os\logs\post_close_console.log -Tail 200
```

확인할 것:

```text
.venv\Scripts\python.exe not found
src\main.py not found
Finished ... with exit code 1
Traceback
ModuleNotFoundError
```

#### 3단계 — Python 내부 로그 확인

```powershell
Get-Content C:\trading\personal_trading_os\logs\post_close.log -Tail 200
```

확인할 것:

```text
config_load / price_collection / indicator_calculation / event_collection
market_regime / watchlist_ranking / setup_matching / risk_engine
output_generation / telegram_send
Serious failures / Unhandled serious failure
```

#### 4단계 — output 생성 여부 확인

```powershell
Get-ChildItem C:\trading\personal_trading_os\output |
  Select-Object Name, LastWriteTime, Length |
  Sort-Object LastWriteTime -Descending
```

#### 5단계 — Python / BAT 직접 실행으로 재현

```powershell
Set-Location C:\trading\personal_trading_os
.\.venv\Scripts\python.exe src\main.py --session post_close
.\run_post_close.bat
$LASTEXITCODE
```

#### 6단계 — Task Scheduler Operational 로그 확인

```powershell
Get-WinEvent -LogName Microsoft-Windows-TaskScheduler/Operational -MaxEvents 100 |
  Where-Object { $_.Message -like "*PersonalTradingOS*" } |
  Select-Object TimeCreated, Id, LevelDisplayName, Message |
  Format-List
```

---

### 21.9 수동 실행은 성공하지만 Task Scheduler만 실패할 때

```text
1. Task Scheduler가 다른 사용자 계정으로 실행됨
2. 권한 문제
3. .env가 프로젝트 루트에 없거나 읽히지 않음
4. 네트워크가 작업 실행 시점에 준비되지 않음
5. 절전/전원 상태 문제
```

현재 BAT 파일은 `cd /d C:\trading\personal_trading_os`를 포함하므로 working directory 문제는 방지된다.

#### .env 존재 및 설정 확인 (값 노출 없이)

```powershell
Test-Path C:\trading\personal_trading_os\.env

Get-Content C:\trading\personal_trading_os\.env | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') {
        if ($matches.value.Length -gt 0) {
            "$($matches.key)=<set>"
        } else {
            "$($matches.key)=<empty>"
        }
    }
}
```

#### 가상환경 및 패키지 확인

```powershell
Test-Path C:\trading\personal_trading_os\.venv\Scripts\python.exe

C:\trading\personal_trading_os\.venv\Scripts\python.exe --version

C:\trading\personal_trading_os\.venv\Scripts\python.exe -c "import pandas, yfinance, yaml, dotenv, requests; print('OK')"
```

#### Task Scheduler GUI 확인 항목

```text
Task Scheduler → Task Scheduler Library → PersonalTradingOS_PostClose → Properties

General:
- Run only when user is logged on 권장
- Configure for: Windows 10 또는 Windows 11

Actions:
- Program/script: C:\trading\personal_trading_os\run_post_close.bat

Conditions:
- Start the task only if the computer is on AC power → 필요 시 해제
- Wake the computer to run this task → 필요 시 체크

Settings:
- Allow task to be run on demand 체크
```

---

### 21.10 작업 삭제/재등록 명령어

```powershell
# 삭제
schtasks /Delete /TN "PersonalTradingOS_PostClose" /F
schtasks /Delete /TN "PersonalTradingOS_PreMarket" /F

# Post-close 재등록
schtasks /Create /TN "PersonalTradingOS_PostClose" /TR "C:\trading\personal_trading_os\run_post_close.bat" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 06:50 /F

# Pre-market 재등록 (서머타임)
schtasks /Create /TN "PersonalTradingOS_PreMarket" /TR "C:\trading\personal_trading_os\run_pre_market.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 21:00 /F

# Pre-market 재등록 (표준시간)
schtasks /Create /TN "PersonalTradingOS_PreMarket" /TR "C:\trading\personal_trading_os\run_pre_market.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 22:00 /F

# 재등록 확인
schtasks /Query /TN "PersonalTradingOS_PostClose" /V /FO LIST
schtasks /Query /TN "PersonalTradingOS_PreMarket" /V /FO LIST
```

---

### 21.11 Windows 시간대 확인

Task Scheduler는 Windows 로컬 시간 기준으로 실행된다.

```powershell
Get-TimeZone
tzutil /g
Get-Date
```

정상 예시:

```text
Korea Standard Time
```

시간대가 다르면 관리자 PowerShell에서 변경한다.

```powershell
tzutil /s "Korea Standard Time"
```

---

### 21.12 최종 운영 체크리스트

#### 최초 등록 전

```text
[ ] C:\trading\personal_trading_os 경로 확인
[ ] .venv\Scripts\python.exe 존재 확인
[ ] requirements 설치 확인
[ ] .env 존재 확인 (값은 <set>/<empty>로만 확인)
[ ] config 파일 존재 확인
[ ] data\manual_news_notes.md 존재 확인
[ ] run_post_close.bat 확인
[ ] run_pre_market.bat 확인
[ ] output/, logs/, cache/가 .gitignore에 포함되어 있는지 확인
```

#### 수동 테스트

```text
[ ] Python 직접 실행 post_close 성공
[ ] Python 직접 실행 pre_market 성공
[ ] run_post_close.bat 성공 ($LASTEXITCODE = 0)
[ ] run_pre_market.bat 성공 ($LASTEXITCODE = 0)
[ ] output 필수 파일 생성 확인
[ ] logs\post_close.log 확인
[ ] logs\post_close_console.log 확인
[ ] logs\pre_market.log 확인
[ ] logs\pre_market_console.log 확인
```

#### Task Scheduler 등록 후

```text
[ ] PersonalTradingOS_PostClose 등록 확인
[ ] PersonalTradingOS_PreMarket 등록 확인
[ ] schtasks /Run으로 즉시 실행 확인
[ ] Last Result 0x0 확인
[ ] Task Scheduler Operational 로그 확인
[ ] Telegram 수신 확인
```

#### 운영 중 문제 발생 시

```text
[ ] schtasks /Query로 Last Result 확인
[ ] *_console.log 확인
[ ] Python 내부 *.log 확인
[ ] output 파일 생성 시간 확인
[ ] Python 직접 실행으로 재현
[ ] BAT 직접 실행으로 재현
[ ] Task Scheduler Operational 로그 확인
[ ] 필요 시 작업 삭제 후 재등록
```

---

### 21.13 최종 운영 구성

```text
Post-close:
  Task Name : PersonalTradingOS_PostClose
  Schedule  : 화~토 06:50 KST
  BAT       : run_post_close.bat
  Session   : post_close
  Python log: logs\post_close.log
  Console log: logs\post_close_console.log

Pre-market:
  Task Name : PersonalTradingOS_PreMarket
  Schedule  : 서머타임 월~금 21:00 KST / 표준시간 월~금 22:00 KST
  BAT       : run_pre_market.bat
  Session   : pre_market
  Python log: logs\pre_market.log
  Console log: logs\pre_market_console.log
```

아래 순서가 모두 통과하면 Windows Task Scheduler 운영 단계 완료:

```text
1. Python 직접 실행 성공
2. BAT 직접 실행 성공
3. schtasks /Run 성공
4. 정시 자동 실행 성공
5. output 필수 파일 생성 확인
6. logs 파일 생성 확인
7. Telegram 수신 확인
```
