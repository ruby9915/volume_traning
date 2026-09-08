# Handoff: 볼륨트레이닝 앱 — 다크(IRON)/라이트(FRESH) 테마 리디자인

## Overview
웨이트 볼륨(중량×횟수×세트) 트래킹 웹앱의 UI 리디자인.
- **다크 모드 = "IRON"** (시안 2a): 헤비한 짐 감성, 웜 블랙 + 오렌지레드 액센트, Oswald 숫자
- **라이트 모드 = "FRESH"** (시안 2b): 클린한 카드 UI, 에메랄드 액센트, Space Grotesk 숫자

대상 화면: 기록(Log), 분석(Dashboard). 이력(History)·종목(Exercises)은 동일 토큰/패턴으로 확장.

## About the Design Files
이 번들의 `디자인 탐색.dc.html`(+`support.js`)은 **HTML로 만든 디자인 레퍼런스**입니다. 브라우저로 열면 시안이 보입니다(같은 폴더에 두 파일이 함께 있어야 함). 프로덕션 코드가 아니며 그대로 복사하지 마세요. 할 일은 이 디자인을 **기존 코드베이스 환경에서 재구현**하는 것입니다.

**대상 코드베이스**: React(Vite) + TypeScript + Tailwind CSS v4 + FastAPI/SQLite.
- 테마 토큰은 `frontend/src/index.css`의 `@theme` 블록에 정의되어 있음 (`--color-bg`, `--color-surface`, `--color-accent` 등) — 이 토큰들을 아래 Design Tokens로 교체/이원화
- 기존 컴포넌트(`Button.tsx`, `Card.tsx`, `BottomSheet.tsx`, `TabBar.tsx`, `Stepper` 패턴 등)와 React Query 데이터 흐름은 유지하고 스타일만 재작업
- 참조 시안: 파일 내 앵커 `#2a`(IRON 기록+분석), `#2b`(FRESH 기록+분석). `#1a~#1d`는 이전 탐색 버전이므로 무시.

## Fidelity
**High-fidelity.** 색·타이포·간격·라운딩을 시안 그대로 재현할 것. 단, 목업 데이터(12,480kg 등)는 실데이터 바인딩.

## Theme Architecture
- 두 테마는 **동일한 레이아웃/컴포넌트 구조**를 공유하고 토큰만 다름. CSS 변수(또는 Tailwind v4 `@theme` + `.dark` variant)로 구현.
- 기본값: `prefers-color-scheme` 따르고, 설정에서 수동 토글(라이트/다크/시스템) 제공. 선택은 `localStorage` 저장.
- 숫자 폰트도 테마 토큰으로: 다크=Oswald, 라이트=Space Grotesk (`--font-numeric`). 구현 단순화를 원하면 한 폰트로 통일 가능하나, 시안 기준은 테마별 폰트.
- 한글/본문은 시스템 고딕 스택 유지: `system-ui, -apple-system, "Noto Sans KR", sans-serif`.
- 숫자 폰트는 Google Fonts (Oswald 400–700, Space Grotesk 400–700). 셀프호스팅 권장(연구실 서버 + Tailscale 환경이므로 오프라인 대비).

## Screens / Views

### 1. 기록 (Log) — 앱 진입 기본 탭
목적: 운동 중 한 손으로 세트를 빠르게 입력. 히트타깃 최소 44px.

**레이아웃** (모바일 단일 컬럼, 좌우 패딩 18px, 섹션 gap 12px):
1. **헤더** — 좌: 날짜 라벨 + 오늘 총 볼륨(대형 숫자) + 보조 메타(경과시간·세트수), 우: "완료" 버튼
   - 다크: 요일 태그(Oswald 11px, letter-spacing 2px, bg accent, 텍스트 bg색, radius 3px) + "07.21 · 가슴" 뮤트 라벨; 볼륨 숫자 Oswald 700 48px, 단위 "KG" 15px muted; 완료 버튼 surface(#171512) radius 10px, 12px 600
   - 라이트: "7월 21일 (화) · 가슴" 12px 600 muted; 볼륨 Space Grotesk 700 40px letter-spacing -1px, "kg" 14px muted; 완료 버튼 잉크색(#17211b) 필, radius 999px, 흰 텍스트 12px 700
2. **완료된 종목 카드** (종목당 1개) — 종목명 + 세트 요약 한 줄("60×10 · 80×8 …", 숫자폰트, muted) + 우측 세트수 뱃지
   - 다크: bg #12100e, radius 14px, 테두리 없음, 우측 "4 SETS" Oswald 12px muted
   - 라이트: bg #fff, radius 16px, shadow `0 1px 2px rgba(23,33,27,.05)`, 우측 "✓ 4" accent 700
3. **진행중 종목 카드** (핵심 인터랙션 영역):
   - 다크: bg #171512, radius 18px, `box-shadow: 0 0 0 1px #ff4a1f33, 0 12px 30px rgba(0,0,0,.4)`; 헤더 우측 8px 오렌지 글로우 도트(진행중 표시)
   - 라이트: bg #fff, radius 22px, `box-shadow: 0 8px 24px rgba(15,169,111,.14)`; "진행중" 필 뱃지(bg accent, 흰 텍스트 10px 700, radius 999px)
   - 내부 구성 (gap 12~13px):
     a. 종목명 (다크 17px 700 / 라이트 16px 800)
     b. **완료 세트 행 리스트** — 행: bg 웰색(다크 #12100e / 라이트 #f4f6f3), radius 9~11px, padding 8~9px 12px; 세트번호(다크: muted 숫자 / 라이트: 18px 원형 accent 체크뱃지) + "중량 × 횟수"(숫자폰트 600) + PR 뱃지(있으면) + 우측 세트볼륨 muted
     c. PR 뱃지: 다크 = bg #ff4a1f, 텍스트 #0c0b0a, 10px 700, radius 3px / 라이트 = bg #eab308, 흰 텍스트 9px 800, radius 999px
     d. 지난 세션 힌트 한 줄: "지난번 7/18 — 24×10 · 26×8 · 26×8" (10px, faint)
     e. **스테퍼 2개** (중량 flex 1.4 : 횟수 flex 1) — 웰(bg 다크 #0c0b0a / 라이트 #f4f6f3, radius 14~16px, padding 10px) 안에 라벨(9~10px) + [− 값 ＋]; 값: 숫자폰트 다크 44px 600 / 라이트 36px 700; ± 버튼: 다크 = 배경없음 accent 텍스트 28px, 44×48px / 라이트 = 흰 카드 버튼 radius 12px shadow, 44×44px
     f. 중량 스테퍼 아래 **±2.5 퀵칩** 2개 (다크: bg #171512 radius 5px Oswald 11px muted / 라이트: bg #0fa96f14 텍스트 accent radius 999px 11px 600)
     g. **세트 완료 버튼** (전폭): 다크 = bg #ff4a1f, 텍스트 #0c0b0a, 58px 높이, radius 14px, 17px 800 / 라이트 = bg #0fa96f, 흰 텍스트, 56px, radius 16px, 16px 800, shadow `0 6px 16px rgba(15,169,111,.3)`; 라벨에 다음 세트 번호 표시 ("세트 완료 · 3")
     h. **휴식 타이머** — "REST/휴식" 라벨 + "01:24 / 02:00"(경과는 텍스트색, 목표는 faint) + 진행바(다크: 3px 트랙 #0c0b0a 필 accent / 라이트: 4px 트랙 #e3e7e1 필 accent, radius 2px)
4. **종목 추가 버튼** — 대시드 보더(다크 #2a2620 / 라이트 1.5px #cdd6cc), radius 14~16px, 높이 48px, muted 텍스트
5. **하단 탭바** — 기록/분석/이력/종목 4탭, 활성 = accent 700, 비활성 = muted; 상단 헤어라인(다크 #1c1916 / 라이트 #e3e7e1); 라이트는 탭바 bg #fff

### 2. 분석 (Dashboard)
목적: 주간/월간 볼륨 추이와 부위 분배를 한눈에.

**레이아웃** (gap 12~16px):
1. **헤더** — 좌 타이틀(다크: "ANALYTICS" Oswald 13px letter-spacing 3px muted / 라이트: "분석" 19px 800), 우 주간/월간 세그먼트 토글(다크: bg #171512 radius 9px, 활성 세그먼트 bg #0c0b0a / 라이트: bg #fff radius 999px shadow, 활성 = 잉크 필 + 흰 텍스트)
2. **히어로 카드** — 이번 주 볼륨 대형 숫자 + 전주 대비 % + 12주 바 차트
   - 다크: bg #171512 radius 18px; 숫자 Oswald 58px 700, "▲12.4%" accent 옆 배치
   - 라이트: **잉크 다크 카드**(bg #17211b, 흰 텍스트) radius 22px; 숫자 Space Grotesk 46px, % 는 #3ddc97
   - 차트: 바 gap 4~5px, radius 3px; 과거→현재로 밝아지는 3단계 톤(다크: #2a2620→#3a332b→#4a4136 / 라이트 히어로 안: #2e3d33→#3a4d40→#46604e); **현재 주 바만 accent**(다크: `linear-gradient(180deg,#ff4a1f,#c2410c)` / 라이트: #3ddc97) + 바 위에 값 라벨("48.9k", 숫자폰트 10~11px accent); x축 라벨 3개(시작/중간/끝, 9px faint)
3. **요약 스탯 3칸** (세션/세트/PR) — 카드 3개 flex, 라벨 10~11px muted + 값 숫자폰트 24~28px; PR 칸 강조(다크: `linear-gradient(160deg,#2a1510,#171512)` bg + accent 텍스트 / 라이트: 라벨만 #eab308)
4. **부위별 분배 카드** — 행: 부위명(한글, 34px 고정폭) + 수평 바 + 값("14.2k", 숫자폰트 muted, 우측정렬 36~40px)
   - 다크: 트랙 #0c0b0a radius 3px 높이 12px, 필 = accent에서 어두워지는 램프(#ff4a1f→#e0491f→#b8431f→#8a3d24→#5c3a2c)
   - 라이트: 트랙 #f0f2ef radius 999px 높이 10px, 필 = 에메랄드 램프(#0fa96f→#26b583→#48c197→#7ed3b2→#aee3cc)
5. **최근 PR 카드** — 종목명 + "중량 PR · 날짜" 캡션 + 우측 기록값(숫자폰트)

### 3. 이력(History)·종목(Exercises) — 시안 없음, 패턴 확장
- 이력: 완료 종목 카드와 동일한 리스트 카드 패턴(날짜 헤더 + 세션 카드: 총볼륨 숫자폰트 강조 + 종목 요약 줄)
- 종목: 검색 + 부위 필터 칩(radius 999px) + 종목 행(이름 + 최근 PR 값)
- 기존 코드의 BottomSheet(종목 선택, RPE 등)는 카드 토큰(surface/radius/shadow)만 테마에 맞춰 재스킨

## Interactions & Behavior
- **스테퍼**: 탭 = 중량 ±(종목별 증분, 기본 2.5), 횟수 ±1; 길게 누르면 반복 증가(기존 구현 유지). 퀵칩 = ±2.5 즉시 적용. 값 직접 탭하면 숫자 키패드 입력(기존 동작 유지)
- **세트 완료**: 탭 → 세트 행 추가(체크 상태) → 휴식 타이머 자동 시작 → 스테퍼 값은 직전 세트 값 유지. 완료 순간 버튼 살짝 스케일다운(transform .1s)
- **PR 감지**: 저장 시 서버 판정 → 세트 행에 PR 뱃지 페이드인
- **휴식 타이머**: 진행바 width 1s linear 갱신; 목표 초과 시 다크는 진행바 유지+시간 텍스트 accent로, 라이트는 동일 패턴
- **차트**: 바 탭 → 해당 주 값 라벨 표시(현재 주는 상시 표시). 주간/월간 토글 시 바 높이 transition .3s ease
- **탭 전환**: 기존 라우팅 유지; 활성 탭 색 전환만
- **테마 전환**: 토큰 스왑, transition 없이 즉시(차트 등 애니메이션 꼬임 방지)
- **호버**(데스크톱): 버튼 brightness(1.08), 카드 리스트 행 bg 한 단계 밝게/어둡게

## State Management
기존 React Query 구조 유지. 추가 상태:
- `theme: "light" | "dark" | "system"` — localStorage persist, `<html>`에 클래스 적용
- 진행중 종목/세트 draft, 휴식 타이머(시작 timestamp 기반 — 백그라운드 복귀 시 재계산)은 기존 로직 재사용

## Design Tokens

### 공통
- 본문 폰트: `system-ui, -apple-system, "Noto Sans KR", sans-serif`
- 페이지 좌우 패딩 18px(360px 기준) / 카드 내부 패딩 16~18px / 섹션 gap 12px(기록), 12~16px(분석)
- 히트타깃 최소 44px, 주 버튼 높이 56~58px
- 숫자 위계: 페이지 히어로 40~58px > 스테퍼 값 36~44px > 스탯 24~28px > 세트 행 14~15px > 요약/캡션 11~12px

### 다크 "IRON" (숫자폰트: Oswald)
| 토큰 | 값 |
|---|---|
| bg | #0c0b0a |
| surface (카드) | #171512 |
| surface-sunken (완료카드·세트행) | #12100e |
| well (스테퍼 트랙) | #0c0b0a |
| border | #2a2620 · 헤어라인 #1c1916 |
| text | #f2ede6 · secondary #c9c2b6 · muted #8a8378 · faint #6e675c |
| accent | #ff4a1f · deep #c2410c · glow #ff4a1f33 |
| PR 뱃지 | bg #ff4a1f / text #0c0b0a |
| 부위 바 램프 | #ff4a1f #e0491f #b8431f #8a3d24 #5c3a2c |
| radius | 카드 18 · 서브카드 14 · 세트행 9 · 칩 5 · 태그 3 |
| 라이브 카드 그림자 | `0 0 0 1px #ff4a1f33, 0 12px 30px rgba(0,0,0,.4)` |

### 라이트 "FRESH" (숫자폰트: Space Grotesk)
| 토큰 | 값 |
|---|---|
| bg | #f4f6f3 |
| surface (카드) | #ffffff |
| well (세트행·스테퍼) | #f4f6f3 |
| border | #e3e7e1 · 대시드 #cdd6cc |
| text/ink | #17211b · muted #71806f · faint #9aa89a |
| accent | #0fa96f · tint #0fa96f14 (8% 배경용) |
| 히어로 다크카드 | bg #17211b · muted #9db3a2 · 차트강조 #3ddc97 |
| PR 뱃지 | bg #eab308 / 흰 텍스트 |
| 부위 바 램프 | #0fa96f #26b583 #48c197 #7ed3b2 #aee3cc |
| radius | 라이브카드 22 · 카드 16~18 · 세트행 11 · 필/칩 999 |
| 그림자 | 카드 `0 1px 3px rgba(23,33,27,.06)` · 라이브 `0 8px 24px rgba(15,169,111,.14)` · 주버튼 `0 6px 16px rgba(15,169,111,.3)` |

### Tailwind v4 매핑 예시
`index.css`의 `@theme`을 라이트 기본값으로 교체하고, 다크는 `@custom-variant dark` + `.dark` 클래스(또는 `[data-theme=dark]`)에서 같은 변수 재정의. 컴포넌트는 `bg-surface text-muted` 식 시맨틱 클래스만 사용해 테마 무관하게 유지.

## Assets
- 외부 이미지/아이콘 없음. 뱃지·도트·바 전부 CSS. 체크는 텍스트 "✓".
- 폰트: Google Fonts — Oswald(400/500/600/700), Space Grotesk(400/500/600/700)

## Screenshots
- `screenshots/dark-iron-2a.png` — 다크 IRON: 좌 기록, 우 분석
- `screenshots/light-fresh-2b.png` — 라이트 FRESH: 좌 기록, 우 분석

## Files
- `디자인 탐색.dc.html` — 시안 문서. 브라우저로 열기(같은 폴더의 `support.js` 필요). **구현 기준은 `#2a`(다크)와 `#2b`(라이트)**; `#1a~#1d`는 탐색 과정의 이전 버전
- 각 시안은 좌측 폰 = 기록 화면, 우측 폰 = 분석 화면
