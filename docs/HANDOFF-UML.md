# UML 과제 핸드오프 — 다른 AI 세션에서 이어가기 위한 컨텍스트

- 작성일: 2026-09-21
- 목적: "소프트웨어 분석 설계" 강의 팀 과제(유즈케이스를 포함한 UML 다이어그램 설계)에 이 저장소의 앱을 주제로 쓰기 위해 2026-09-15 ~ 09-20 사이 Claude와 나눈 논의를 정리한 것. 이 파일 하나로 다른 AI가 문맥을 이어받을 수 있게 썼다.
- 이 파일이 참조하는 저장소 파일: `SETTING.MD`(설계 정본, §1~§14), `장기목표.md`(헬스장 네트워크 비전), `docs/HANDOFF-v2.1.md`, `backend/app/db.py`(스키마), `backend/app/routers/*.py`(API), `frontend/src/api/types.ts`(프론트·백엔드 계약 정본).
- 팀 공유용 설계서(Claude Doc, 사람이 열어 보는 용도): https://claude.ai/code/artifact/e0707ab5-0f30-4b6a-b9c0-c1532b6597a4 — 내용은 이 파일 §7에 옮겨 두었다.

---

## 1. 프로젝트 한 줄 요약과 현재 상태

헬스장에서 세트 사이에 폰으로 중량·횟수를 입력하면 볼륨(중량 × 횟수)을 자동 계산하고 주간·부위별·종목별로 분석하는 웨이트 트레이닝 기록 웹앱. React(Vite, TypeScript) + FastAPI(Python) + SQLite(raw sqlite3, ORM 없음). 연구실 Windows PC에서 Task Scheduler로 상시 구동, Tailscale Funnel로 공개 URL.

| 항목 | 값 (2026-09-21 기준) |
|---|---|
| 버전 | v2.4 (SETTING.MD §14 운동 방식 태그) |
| 스키마 | `PRAGMA user_version` 8 (v1→v8 마이그레이션 누적) |
| 백엔드 테스트 | pytest 170개 (API 계약 테스트 포함) |
| 종목 라이브러리 | 내장 391종 (`seed_data/exercises.py`) |
| 머신 아카이브 | 1,735대, 9개 브랜드, 단종 포함 (`seed_data/machines.py`) |
| 사용자 | 개발자 본인 + 지인 계정 (다중 사용자, 관리자 1) |
| GitHub | https://github.com/ruby9915/volume_traning (branch main) |

## 2. 과제 조건 (알려진 것)

- 강의: 소프트웨어 분석 설계. 과제: 유즈케이스를 포함한 UML 다이어그램 설계 프로젝트. 팀 과제.
- 단계: 주제 선정 중(2026-09-20 기준). 마감일·중간 점검일·팀 인원·요구 다이어그램 종류는 아직 확인되지 않았다 → 다른 AI는 이걸 먼저 물어보는 게 좋다.

## 3. 논의 경과 (시간순)

1. **2026-09-15 사진으로 머신 식별 기능 논의.** 사용자 제안은 "파인튜닝한 이미지 에이전트로 사진 → DB 자동 등록". 합의된 대안: 파인튜닝 없이 범용 비전 모델(Claude API 이미지 입력, 기본 모델 `claude-opus-5`) 제로샷으로 명판·로고·기구 형태를 읽고 → 기존 아카이브 검색과 대조 → 미적중이면 web search로 제조사 표기 확인 → AI가 채운 폼을 **사용자가 확인·수정한 뒤** 기존 `POST /api/machines`로 등록. 자동 반영 금지 이유: `machine`은 `UNIQUE(brand, model)`이고 배포된 튜플 문자열은 바꾸지 않는 규칙이라 오독 = 중복행. 비용 추정 장당 $0.02~0.05. 상용화 시 월 구독 포함 + 월 쿼터(무료 3장/구독 30장 안) + 헬스장 단위 캐시 + 호출 전 필터(리사이즈·pHash·Haiku 게이트) + 이중 지출 상한. 사진은 저장하지 않는다.
2. **2026-09-15 경쟁 서비스 조사.** 해외에 GymScan, Gymeo, GymVision, GymLensIQ, Spotter, Fitzi 등 "머신 스캐너" 앱이 있으나 전부 **머신 종류**(레그 프레스 등) 식별 + 사용법 안내 수준이고 브랜드·모델 단위 식별·기록 연결은 없음. 전부 범용 비전 모델 기반, 스캔은 구독 뒤. 국내에는 같은 기능 없음. 플랜핏이 "다니는 헬스장 등록 → 그 기구로만 루틴"을 제공(월 ₩10,900~13,900). 하드웨어형(Technogym QR, EGYM NFC)은 해당 브랜드 기구가 있는 헬스장에서만.
3. **2026-09-15 `장기목표.md` 작성.** 사용자 비전: 헬스장 등록(1일권은 위치 기반) → 사진으로 머신 등록 → 헬스장별 머신 목록 → 전국 헬스장·머신 데이터 → 설치·사용 데이터 B2B. 평가: API 절감은 동의(콜드스타트 제외), 설치 데이터 판매는 후순위 upside, 사용 데이터 판매는 가치 높지만 opt-in·익명화·규모 필요. 리스크: 위치정보법 신고 가능성, 크라우드소싱 품질.
4. **2026-09-20 과제 적합성 평가.** 결론: 소재로 충분히 좋고 관건은 범위 자르기. LLM은 UML상 **보조 액터**(시스템이 호출하는 외부 시스템)로 두는 것이 정확하며, 주 액터로 그리면 틀림(LLM은 먼저 말을 걸지 않는다). 현재 앱에 LLM 연동 코드는 없으므로 보고서에 "설계 단계"로 명시.
5. **2026-09-20 팀 공유용 장점 리스트 + 설계서(Claude Doc) 작성.** 내용은 §7.

## 4. 합의된 설계 결정 (UML 관점)

- **구성**: 기존 앱(v2.4)을 as-is 문맥으로 두고, 신규 기능(사진으로 머신 식별, 헬스장 등록)을 to-be로 정식 분석·설계한다. 기존 부분은 코드·스키마와 대조 가능한 추적성(유즈케이스 → API → 테이블)을 보여 준다.
- **액터**
  - 주 액터: 일반 사용자, 관리자, 친구(읽기 전용 열람자)
  - 보조 액터: AI 비전 서비스(Claude API, 이름은 "AI 조언자" 가능), 장소 API(Kakao Local 등, to-be), 스케줄러(시간 액터: 백업·자동 기동)
- **유즈케이스 후보 8개**: 가입·로그인 / 세트 기록(오프라인 포함) / 이력 조회·편집 / 종목 관리 / 내 머신 관리 / 사진으로 머신 식별·등록 / 분석 조회(4주 게이트) / 친구 요청·공유
- **깊게 다룰 2개(제안, 팀 확인 대기)**: 세트 기록, 사진으로 머신 식별
- **다이어그램 계획**: 유즈케이스 1, 클래스(도메인) 1, 시퀀스 2(세트 기록·사진 식별), 상태 1(outbox 항목 또는 친구 관계), 활동 1(분석 게이트), 배포 1
- **관계**: "사진으로 머신 식별" «extend» "내 머신 추가"(선택 경로). "세트 기록" «include» "세션 확보(오늘 세션 없으면 생성)".
- **사진 식별의 대체 흐름 목록**: 인식 실패 / 낮은 신뢰도 / 월 쿼터 초과 / API 장애·타임아웃 / 안전 거부(`stop_reason: refusal`) / 아카이브 중복(409) / 사용자가 폼에서 취소
- **비기능 요구사항(숫자로 적을 것)**: 사진 1장 비용, 월 쿼터, 응답 시간 수 초, 사진 미저장, 위치 좌표 미저장, 백업 주기, 오프라인 무유실·무중복

## 5. 다이어그램에 필요한 도메인 사실 (코드에서 확인한 것)

### 5.1 테이블 (`backend/app/db.py`)

`user`, `friendship`, `muscle_group`, `machine`, `exercise`, `favorite`, `user_machine`, `exercise_secondary_target`, `workout_session`, `workout_set`, `body_weight_log`. VIEW: `set_volume`, `target_path`, `set_indirect`.

핵심 관계:
- `user` 1 — n `workout_session` 1 — n `workout_set`
- `workout_set` n — 1 `exercise`, n — 1 `muscle_group`(target_id, 세트 볼륨은 타겟에 100% 귀속)
- `workout_set` 열: id, client_id UNIQUE(멱등 키), session_id, exercise_id, set_index, weight_kg, reps, is_warmup, rpe, note, target_id, technique('drop'|'superset'|'compound'|'giant'|'rest_pause'|NULL)
- `muscle_group`: level 2/3 + parent_id (부위 → 세부 부위 계층)
- `exercise` n — 1 `muscle_group`(default_target), `exercise_secondary_target`로 보조 근육 n:m
- `machine(brand, model UNIQUE, name_ko, target_id)`, `user_machine(user_id, machine_id)` = "내 머신"
- `favorite(user_id, exercise_id)`
- `friendship(requester_id, addressee_id, status, created_at, responded_at)` — status는 `'pending'` → `'accepted'`. 거절과 친구 끊기는 행 DELETE(별도 상태 없음).
- `body_weight_log(user_id, date UNIQUE)`
- to-be(장기목표.md §3 초안): `gym`, `user_gym`, `gym_machine`, `machine.source`, `recognition_log`

### 5.2 API 라우터 (`backend/app/routers/`)

`sessions`(세션·세트), `exercises`, `catalog`(targets·machines·me/machines), `stats`, `analytics`(`/api/stats/advanced/*`), `friends`, `admin`. 인증은 `backend/app/auth.py`(`/api/auth/register·login·me·password`, JWT 90일). 관리자 API는 읽기 전용. 친구 공유는 GET 핸들러가 `?user_id=`를 `subject_user`로 처리, 쓰기는 본인 전용.

### 5.3 오프라인 outbox (SETTING.MD §5.4, `frontend/src/api/client.ts`)

세트 저장 요청은 localStorage `vt_outbox`에 먼저 기록 → 전송 성공 시 제거. 앱 로드·`online` 이벤트 시 flush. 각 세트는 클라이언트 UUID `client_id`로 서버가 멱등 처리(재전송해도 중복 없음). 401 수신 시 flush 중지·큐 보존 → 재로그인 후 재개. 상태 다이어그램용 상태: 대기 → 전송 중 → 제거(성공) / 대기(실패·오프라인) / 보류(401) → 재로그인 → 대기.

### 5.4 분석 게이트 (`routers/stats.py`, `routers/analytics.py`)

`ADVANCED_MIN_WEEKS = 4`. 훈련 주(웜업 아닌 세트가 있는 ISO 주) 수가 4 미만이면 `/api/stats/advanced/*` 전체가 `403 {code: "insufficient_data", weeks_of_data, required_weeks}`. 라우터 수준 의존성 `require_analytics_ready`라 핸들러가 빠뜨릴 수 없다. 활동 다이어그램용 분기.

### 5.5 배포 (SETTING.MD §7, §12)

React SPA(빌드 결과를 FastAPI가 정적 서빙) — FastAPI(uvicorn, 127.0.0.1:8000) — SQLite 파일. Windows Task Scheduler가 최고 권한으로 기동, Tailscale Funnel이 443 → 8000. 백업은 쓰기 감지 → 디바운스 → `VACUUM INTO` 스냅샷을 OneDrive 폴더로. 재시작은 `schtasks /End` + `/Run` 경유만.

## 6. 유즈케이스 명세 초안 (다른 AI가 확장할 출발점)

### UC-02 세트 기록
- 주 액터: 일반 사용자. 보조: 없음.
- 사전조건: 로그인 상태. 오늘 세션이 없어도 됨(«include» 세션 확보).
- 기본 흐름: 종목 선택(즐겨찾기·검색·최근) → 타겟 부위 확인(종목 기본값, 세트별 변경 가능) → 중량·횟수 입력(웜업·운동 방식 선택) → 저장 → 목록에 표시, 휴식 타이머 시작.
- 대체 흐름: A1 네트워크 없음 → outbox 대기, 회색+스피너 표시, 복구 시 자동 전송. A2 타임아웃 후 재전송 → `client_id`로 서버가 중복 무시. A3 401 → 큐 보존, 재로그인 후 재개. A4 입력 검증 실패(reps ≤ 0, weight < 0) → 저장 거부.
- 사후조건: 세트가 세션에 속하고 볼륨·PR·분석에 반영.

### UC-06 사진으로 머신 식별·등록 (to-be)
- 주 액터: 일반 사용자. 보조 액터: AI 비전 서비스, (미적중 시) web search.
- 사전조건: 로그인, 이번 달 쿼터 잔여, 카메라 권한.
- 기본 흐름: 내 머신 추가 화면에서 "사진으로 찾기" → 촬영 → 클라이언트 리사이즈(긴 변 1,568px) → 서버 `POST /api/machines/identify` → AI가 {brand, model_text, machine_type, confidence} 추출 → 서버가 아카이브 검색 → 후보 목록 표시 → 사용자가 하나 선택 또는 새 항목 폼 확인·수정 → 기존 `POST /api/machines` 또는 `POST /api/me/machines` → 내 머신에 추가.
- 대체 흐름: A1 인식 실패(머신 아님·흐림) → 재촬영 안내, 쿼터 미차감. A2 낮은 신뢰도 → 후보 대신 검색창으로 유도. A3 쿼터 초과 → 검색으로 안내. A4 API 장애·타임아웃 → 오류 표시, 재시도. A5 안전 거부 → 검색으로 안내. A6 아카이브 중복(409) → 기존 항목을 내 머신에 담기. A7 사용자 취소.
- 비기능: 사진은 처리 후 폐기. 응답 수 초. 장당 비용·월 쿼터 기록(`recognition_log`).
- 사후조건: 아카이브에 항목 존재(신규면 `source='photo'`), 사용자의 내 머신에 등록.

## 7. 팀 공유 설계서 요약 (Claude Doc 내용)

### 7.1 장점
- 요구사항을 상상이 아니라 실사용 경험에서 뽑는다.
- 액터가 억지 없이 6개.
- 유즈케이스마다 대체 흐름이 있다(오프라인, 게이트, 수락·거절).
- 클래스 다이어그램 소재가 실제 스키마로 존재.
- 상태·활동·배포 다이어그램까지 실제 구성으로 채워진다.
- as-is 위에 to-be를 얹는 구성이라 실무 흐름과 같다.
- 설계서·API 명세·커밋 이력·테스트가 있어 추적성을 보여 줄 수 있다.
- 도메인 학습 비용이 거의 없고, 발표 때 실제 앱 시연 가능.

### 7.2 단점과 대응
| 단점 | 대응 |
|---|---|
| 기능이 많아 전부 그리면 얕아진다 | 유즈케이스 8개로 자르고 상세 명세는 2개만 깊게 |
| 이미 만들어진 시스템이라 역공학처럼 보일 수 있다 | 기존은 as-is로 짧게, 신규를 to-be로 정식 설계 |
| AI 사진 식별은 코드가 없다 | 설계 단계임을 명시. 사진 20~30장 인식률 측정 스크립트를 돌리면 타당성 자료 |
| 분석 6종은 계산 규칙이라 UML로 보여 줄 게 적다 | 유즈케이스 하나 + 게이트 활동 다이어그램으로만 |
| 개인 프로젝트라 팀 기여가 불균형해 보일 수 있다 | 새 기능 설계를 팀원이 나눠 맡고, 설계 산출물은 전부 새로 만든다 |
| 위치 기반 헬스장 등록은 위치정보법 신고 대상일 수 있다 | 설계 제약사항으로 명시. 비기능 요구사항 사례가 된다 |

### 7.3 평가에서 유리한 점 (일반적인 팀 프로젝트 대비)
요구사항 출처(실사용 vs 가상), 액터 수(6 vs 2), 대체 흐름의 종류, 비결정적 컴포넌트(AI 보조 액터 + human-in-the-loop), 숫자로 적는 비기능 요구사항, 자연스러운 «extend» 사례, 코드·테스트 170개와의 대조 가능성, 장기 확장 절. 조건: 범위를 자르고, AI 액터의 대체 흐름을 명세에 실제로 적을 것.

### 7.4 팀 회의에서 정할 것
- [ ] 주제 확정
- [ ] 유즈케이스 8개 안 채택 또는 조정
- [ ] 깊게 다룰 2개 확정(제안: 세트 기록, 사진 식별. 대안: 사진 식별 + 헬스장 등록)
- [ ] 다이어그램 분담
- [ ] AI 액터 이름·위치
- [ ] 인식률 측정 스크립트 실행 여부와 담당
- [ ] 제출 마감일·중간 점검일

## 8. 다른 AI에게 바로 줄 수 있는 요청 예시

- "docs/HANDOFF-UML.md와 SETTING.MD §5.4·§10.4·§11.1을 읽고, §4의 액터·유즈케이스 8개로 유즈케이스 다이어그램을 PlantUML로 그려줘. «include»·«extend»는 §4의 두 개만."
- "§6의 UC-06을 시퀀스 다이어그램(PlantUML)으로. 참여자: 사용자, 프론트, 서버, AI 비전 서비스, DB. 대체 흐름 A1·A3·A6은 alt 블록으로."
- "§5.1의 테이블로 도메인 클래스 다이어그램을 그려줘. VIEW는 제외, to-be 테이블은 점선 패키지로."
- "§5.3 outbox 항목의 상태 다이어그램을 그려줘."
- "§5.4 분석 게이트를 활동 다이어그램으로."

## 9. 하지 않기로 한 것

파인튜닝, 사진 자동 DB 반영, 사진 저장, 위치 이력 저장, 데이터 판매 계약, LLM을 주 액터로 그리기, RP 랜드마크(MV/MEV/MAV/MRV) 도입.
