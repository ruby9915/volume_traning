# 운동 볼륨 트래킹 앱 — 설계서

- 작성일: 2026-07-19
- 상태: **v1 설계 확정** — 이 문서가 구현의 단일 기준(canonical spec)이다.
- **2026-09-10 외부 공개 방식 개정(§12)**: Tailscale Funnel → **Cloudflare Tunnel**(원격 관리, 내 도메인). 이후 NAS 구축 시 직접 노출(Caddy + 포트포워딩)로 전환 예정. 앱 구조는 불변(127.0.0.1:8000).
- **2026-09-08 v2 개정(§10)**: 다중 사용자(계정·로그인·관리자), 타겟 부위 체계(주동근/보조근 → 세트 타겟 100% 귀속, 3단계 분류), 종목 라이브러리(내장 391종 + 즐겨찾기 + 태그, 이름 자동 조합 폐기), 머신 카탈로그. §1·§3·§4·§5·§6의 해당 항목은 §10이 우선한다.
- 변경 이력: 2026-07-19 배포 방식 변경 — Fly.io 유료 클라우드 → **PC 서버 + Tailscale Funnel(무료)** (사용자 결정, §7). 서버는 **연구실 PC, 24시간 상시 구동** (사용자 확인). 2026-07-22 **종목 속성 체계 추가** (§3.6, 사용자 결정 — 상용앱 조사·시드 백필 시험 후 "속성=분류, 정체성=행, 값=사용자 사전" 형태로 확정)
- 결정 과정: 사용자 문답으로 요구사항 확정 → 데이터 모델 / API / UI / 분석 / 인프라 5개 영역 병렬 설계 → 교차 검토로 모순·누락 정리 후 통합.

---

## 1. 확정 요구사항 (문답 결과)

| 항목 | 결정 |
|---|---|
| 목적 | 웨이트 트레이닝 볼륨(중량×횟수×세트) 기록·분석 |
| 사용자 | 1명 (본인). 단, 공개 인터넷 배포이므로 비밀번호 인증 필수 |
| 플랫폼 | 반응형 웹앱 (모바일 브라우저 우선, PC 겸용). PWA·네이티브 앱 아님 |
| 스택 | 프론트 React(Vite) + 백엔드 Python FastAPI + SQLite |
| 사용 시나리오 | 헬스장에서 세트 사이 휴식 중 폰으로 즉시 입력 → 연구실 PC(24시간 구동) 서버 + 무료 터널로 외부 접속 |
| 기록 단위 | 세션 > 종목 > 세트(중량 kg, 횟수). 볼륨 자동 계산 |
| 종목 | 기본 내장 45종(부위 매핑 포함) + 직접 추가 |
| 분석 | 세트 데이터에서 가능한 분석 최대한 풍부하게 |
| 개발 방침 | **완성품 우선** — 과한 확장성보다 단순하고 확실하게 동작 |

---

## 2. 아키텍처 요약

```
[폰(LTE)/PC 브라우저]
   React SPA (Vite 빌드, 다크 테마 단일)
        │ HTTPS  https://<pc이름>.<tailnet>.ts.net  (/api/* JSON + JWT Bearer)
        ▼
[Tailscale Funnel — 무료, 아웃바운드 터널이라 포트포워딩 불필요]
        ▼
[연구실 PC (Windows 11, 24시간 상시 구동)]
   FastAPI ──서빙──▶ React 정적 빌드 (StaticFiles + SPA fallback)
      │
   SQLite (backend/data/app.db)
      │
   일일 스냅샷 ──▶ 클라우드 드라이브 동기화 폴더 (오프사이트 백업)
```

- **단일 서버 서빙 확정**: FastAPI가 React 빌드 산출물을 서빙. CORS·도메인 분리 문제가 사라지고 배포 유닛이 1개.
- API는 전부 `/api/*` prefix. 그 외 경로는 `index.html` fallback.

### 기술 스택 확정

| 영역 | 선택 | 근거 |
|---|---|---|
| 백엔드 | FastAPI + `sqlite3` 표준 라이브러리 (raw SQL) | 테이블 6개 규모에 SQLAlchemy+Alembic은 과투자. 분석 쿼리는 어차피 SQL 직접 작성이 명확 |
| 마이그레이션 | 없음 — `CREATE TABLE IF NOT EXISTS` + `PRAGMA user_version` | 같은 이유 |
| 패키지 관리 | uv (`pyproject.toml`) | 빠르고 lockfile 자동 |
| 라우팅 | React Router v6 | 8개 라우트 규모에 표준 |
| 서버 상태 | TanStack Query v5 | optimistic update(1탭 세트 입력 UX의 핵심)를 직접 구현 없이 해결 |
| 클라이언트 상태 | Zustand | 활성 종목·스테퍼 값·타이머 등 소량 UI 상태만 필요 |
| 차트 | Recharts | bar/stacked bar/line 기본 제공, 러닝커브 최저 |
| CSS | Tailwind CSS | 모바일 우선·터치 타깃 조정이 가장 빠름. 컴포넌트 라이브러리(MUI 등) 미도입 |

---

## 3. 데이터 모델

### 3.1 엔티티

| 테이블 | 역할 |
|---|---|
| `muscle_group` | 근육 부위 마스터 (시드 고정 12개 + 상위 region 6분류) |
| `exercise` | 종목 마스터 (내장 시드 45종 + 사용자 추가) |
| `exercise_muscle` | 종목–부위 N:M 매핑. `role` = primary/secondary, **복수 primary 허용** (예: 데드리프트) |
| `workout_session` | 운동 세션 (날짜 + 메모). 하루 복수 세션 허용 |
| `workout_set` | 개별 세트 — 기록의 최소 단위 |
| `body_weight_log` | 체중 기록 (맨몸 운동 볼륨 계산용) |

확정 사항:
- "종목별 세트 그룹" 중간 엔티티(entries)는 **두지 않는다**. 세트가 `session_id + exercise_id`를 직접 가지며, 화면의 종목별 그룹핑은 쿼리로 처리.
- **볼륨은 저장하지 않고 파생 계산** (`set_volume` VIEW). 수정·삭제 시 정합성이 공짜로 유지된다.
- 인증은 데이터 모델 밖 (user 테이블 없음, §4.1).

### 3.2 스키마 (DDL)

앱 시작 시 `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`.

```sql
CREATE TABLE muscle_group (
    id         INTEGER PRIMARY KEY,
    code       TEXT    NOT NULL UNIQUE,          -- 'chest', 'quads' 등 안정 식별자
    name_ko    TEXT    NOT NULL,
    region     TEXT    NOT NULL CHECK (region IN
               ('chest','back','shoulders','arms','legs','core')),  -- 상위 6분류 롤업
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE exercise (
    id                INTEGER PRIMARY KEY,
    name_ko           TEXT NOT NULL UNIQUE,
    name_en           TEXT,
    bodyweight_factor REAL NOT NULL DEFAULT 0
                      CHECK (bodyweight_factor >= 0 AND bodyweight_factor <= 1),
                      -- 유효 중량에 포함할 체중 비율. 0=외부 중량만, 1.0=풀업/딥스
    load_multiplier   REAL NOT NULL DEFAULT 1 CHECK (load_multiplier > 0),
                      -- 양손 덤벨 동시 운동 = 2 (입력은 한쪽 덤벨 무게)
    is_builtin        INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0,1)),
    is_archived       INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0,1)),
                      -- 삭제 대신 숨김: 과거 세트 기록 보존
    note              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE exercise_muscle (
    exercise_id     INTEGER NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    muscle_group_id INTEGER NOT NULL REFERENCES muscle_group(id),
    role            TEXT    NOT NULL CHECK (role IN ('primary','secondary')),
    PRIMARY KEY (exercise_id, muscle_group_id)
);
CREATE INDEX idx_exercise_muscle_mg ON exercise_muscle(muscle_group_id);

CREATE TABLE workout_session (
    id         INTEGER PRIMARY KEY,
    date       TEXT NOT NULL,                    -- 'YYYY-MM-DD' (§6.3 하루 경계 03:00 규칙)
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_session_date ON workout_session(date);
-- UNIQUE(date) 없음: 하루 2회 운동(오전/오후) 허용

CREATE TABLE workout_set (
    id          INTEGER PRIMARY KEY,
    client_id   TEXT UNIQUE,                     -- 클라이언트 생성 UUID. 오프라인 재전송 멱등 처리(§5.4)
    session_id  INTEGER NOT NULL REFERENCES workout_session(id) ON DELETE CASCADE,
    exercise_id INTEGER NOT NULL REFERENCES exercise(id),
    set_index   INTEGER NOT NULL,                -- 세션 내 입력 순서
    weight_kg   REAL    NOT NULL DEFAULT 0 CHECK (weight_kg >= 0),
    reps        INTEGER NOT NULL CHECK (reps > 0),
    is_warmup   INTEGER NOT NULL DEFAULT 0 CHECK (is_warmup IN (0,1)),
    rpe         REAL    CHECK (rpe IS NULL OR (rpe >= 1 AND rpe <= 10)),
                        -- 컬럼만 확보. v1에서는 UI 노출·분석 없음
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                        -- 초 단위 저장 필수: v2 세션 길이·휴식 분석의 소급 재료
);
CREATE INDEX idx_set_session  ON workout_set(session_id);
CREATE INDEX idx_set_exercise ON workout_set(exercise_id);

CREATE TABLE body_weight_log (
    id        INTEGER PRIMARY KEY,
    date      TEXT NOT NULL UNIQUE,              -- 'YYYY-MM-DD'
    weight_kg REAL NOT NULL CHECK (weight_kg > 0)
);
```

볼륨 계산을 한 곳에 고정하는 VIEW — **모든 분석 쿼리는 이 VIEW 기반으로 작성한다**:

```sql
CREATE VIEW set_volume AS
SELECT
    ws.id           AS set_id,
    s.id            AS session_id,
    s.date          AS date,
    ws.exercise_id  AS exercise_id,
    ws.is_warmup    AS is_warmup,
    ws.weight_kg    AS weight_kg,
    ws.reps         AS reps,
    ( ws.weight_kg
      + e.bodyweight_factor * COALESCE(
          (SELECT bw.weight_kg FROM body_weight_log bw
           WHERE bw.date <= s.date ORDER BY bw.date DESC LIMIT 1), 0)
    ) * e.load_multiplier * ws.reps AS volume_kg
FROM workout_set ws
JOIN workout_session s ON s.id = ws.session_id
JOIN exercise e        ON e.id = ws.exercise_id;
```

### 3.3 볼륨 계산 규칙 (전 섹션 공통, 단일 정의)

기본식: **`volume = (weight_kg + bodyweight_factor × 최근 체중) × load_multiplier × reps`**

- **맨몸 운동**: `bodyweight_factor`(풀업·딥스 1.0, 푸시업 0.65, 크런치 0.3 등 근사 계수) × "세션 날짜 이전 가장 최근 체중"을 유효 중량에 더한다. `weight_kg`에는 **추가 중량만** 입력(중량 딥스 20kg = weight_kg 20). 계수의 목적은 정밀 역학이 아니라 "맨몸 볼륨이 0으로 왜곡되는 것 방지". 체중 기록이 없으면 0으로 계산되므로 맨몸 종목 최초 선택 시 체중 입력 모달을 띄운다(§5.6).
- **웜업 세트**: 저장하되 기본 집계에서 제외 (`is_warmup=1`, 입력 시 토글). 자동 판정 휴리스틱은 넣지 않는다 — 오판이 데이터 신뢰를 깎는다. 분석 화면에 "웜업 포함" 스위치만 제공.
- **좌우 분리 운동**: (a) 양손 동시 덤벨(덤벨 벤치, 레터럴 레이즈): 한쪽 덤벨 무게 입력 + `load_multiplier=2` — "20kg 덤벨로 벤치"라는 통용 관행과 입력값 일치. (b) 한쪽씩 수행(원암 로우, 불가리안 스플릿 스쿼트): 좌/우 별도 세트, `multiplier=1`.
- **PR·추정 1RM은 `weight_kg`(입력값) 기준** — multiplier·체중 미적용 (덤벨 PR은 한쪽 무게로 말하는 관행과 일치). `weight_kg=0` 세트는 Weight PR·e1RM 대상에서 제외.
- **단위: kg 고정.** 입력은 **0.25kg step 강제** (0.25 배수는 이진 부동소수점에서 정확 표현 → REAL 동등 비교 안전, 1.25 증분과도 호환). 검증 범위: weight 0~500, reps 1~100.
- **부위 귀속 (볼륨·세트 수 공통)**: primary **1.0** / secondary **0.5** 가중. 부위별 합계는 총볼륨과 일치하지 않으므로 차트에 "가중 볼륨"으로 명시.
- **추정 1RM**: **Epley** `e1RM = weight × (1 + reps/30)`. 대상: 웜업 제외 + `1 ≤ reps ≤ 12` + weight > 0. (Brzycki는 고반복에서 과대 추정이 급격해 배제.)
- **시간 기반 운동(플랭크 등)은 v1 스코프 제외** — reps 모델에 초를 욱여넣지 않는다.

### 3.4 부위 분류 (12분류 + 6 region 2계층)

6분류만으로는 "하체"가 사두/햄/둔근 불균형을 숨기고, 근육 단위 세분화는 유지 비용 과다. 요약 차트는 region, 상세 차트는 12분류.

| code | name_ko | region | | code | name_ko | region |
|---|---|---|---|---|---|---|
| chest | 가슴 | chest | | quads | 대퇴사두 | legs |
| back | 등 | back | | hamstrings | 햄스트링 | legs |
| lower_back | 허리(기립근) | back | | glutes | 둔근 | legs |
| shoulders | 어깨 | shoulders | | calves | 종아리 | legs |
| biceps | 이두 | arms | | abs | 복근 | core |
| triceps | 삼두 | arms | | forearms | 전완 | arms |

### 3.5 내장 종목 시드 45종

표기: BW = bodyweight_factor, ×2 = load_multiplier 2, (편측) = 좌우 별도 세트 기록.

| name_ko | name_en | primary | secondary | 비고 |
|---|---|---|---|---|
| 벤치프레스 | Barbell Bench Press | chest | triceps, shoulders | |
| 인클라인 벤치프레스 | Incline Barbell Bench Press | chest | shoulders, triceps | |
| 덤벨 벤치프레스 | Dumbbell Bench Press | chest | triceps, shoulders | ×2 |
| 인클라인 덤벨프레스 | Incline Dumbbell Press | chest | shoulders, triceps | ×2 |
| 체스트 프레스 머신 | Chest Press Machine | chest | triceps | |
| 딥스 | Dips | chest | triceps, shoulders | BW 1.0 |
| 푸시업 | Push-up | chest | triceps, shoulders | BW 0.65 |
| 케이블 크로스오버 | Cable Crossover | chest | — | |
| 펙덱 플라이 | Pec Deck Fly | chest | — | |
| 데드리프트 | Conventional Deadlift | hamstrings, glutes, lower_back | back, quads, forearms | |
| 바벨 로우 | Barbell Row | back | biceps, lower_back | |
| 풀업 | Pull-up | back | biceps | BW 1.0 |
| 친업 | Chin-up | back | biceps | BW 1.0 |
| 랫풀다운 | Lat Pulldown | back | biceps | |
| 시티드 케이블 로우 | Seated Cable Row | back | biceps | |
| 원암 덤벨 로우 | One-arm Dumbbell Row | back | biceps | (편측) |
| 티바 로우 | T-Bar Row | back | biceps | |
| 슈러그 | Barbell Shrug | back | forearms | |
| 백 익스텐션 | Back Extension | lower_back | glutes, hamstrings | BW 0.6 |
| 오버헤드 프레스 | Overhead Press | shoulders | triceps | |
| 덤벨 숄더프레스 | Dumbbell Shoulder Press | shoulders | triceps | ×2 |
| 사이드 레터럴 레이즈 | Lateral Raise | shoulders | — | ×2 |
| 프론트 레이즈 | Front Raise | shoulders | — | ×2 |
| 리어델트 플라이 | Rear Delt Fly | shoulders | back | ×2 |
| 페이스풀 | Face Pull | shoulders | back | |
| 바벨 컬 | Barbell Curl | biceps | forearms | |
| 덤벨 컬 | Dumbbell Curl | biceps | forearms | ×2 |
| 해머 컬 | Hammer Curl | biceps | forearms | ×2 |
| 케이블 푸시다운 | Cable Pushdown | triceps | — | |
| 라잉 트라이셉스 익스텐션 | Lying Triceps Extension | triceps | — | |
| 오버헤드 트라이셉스 익스텐션 | Overhead Triceps Extension | triceps | — | |
| 리스트 컬 | Wrist Curl | forearms | — | |
| 백스쿼트 | Barbell Back Squat | quads, glutes | hamstrings, lower_back | |
| 프론트 스쿼트 | Front Squat | quads | glutes, abs | |
| 레그 프레스 | Leg Press | quads | glutes, hamstrings | |
| 런지 | Dumbbell Lunge | quads, glutes | hamstrings | ×2 |
| 불가리안 스플릿 스쿼트 | Bulgarian Split Squat | quads, glutes | hamstrings | (편측) |
| 루마니안 데드리프트 | Romanian Deadlift | hamstrings, glutes | lower_back | |
| 레그 컬 | Leg Curl | hamstrings | — | |
| 레그 익스텐션 | Leg Extension | quads | — | |
| 힙 쓰러스트 | Hip Thrust | glutes | hamstrings | |
| 스탠딩 카프 레이즈 | Standing Calf Raise | calves | — | |
| 크런치 | Crunch | abs | — | BW 0.3 |
| 행잉 레그 레이즈 | Hanging Leg Raise | abs | forearms | BW 0.5 |
| 케이블 크런치 | Cable Crunch | abs | — | |

- 시드는 FastAPI 기동 시 `is_builtin=1` 기준 `INSERT OR IGNORE`(이름 충돌 시 건너뜀) — 재배포해도 사용자 수정값·추가 종목이 보존된다.
- **내장 종목도 수정 허용** (개인용 — 보호 UI가 오히려 비용). 삭제는 세트 기록이 있으면 `is_archived=1` 처리로 통일.
- 아카이브 종목과 동명 재생성 시 409 대신 **"복원하시겠습니까?" 흐름으로 unarchive 재사용** — 히스토리 연속성 보존.

### 3.6 종목 속성 체계 (2026-07-22 추가)

배경: 사용자가 "운동명은 속성의 조합"이라는 관찰에서 속성 기반 DB를 제안. 상용앱 7종 조사(전원 flat list + 최소 메타데이터)와 시드 45종 백필 시험(엄격 분해 성공 22%) 결과를 반영해, **순수 조합형이 아니라 "속성=분류용 메타데이터, 정체성=행, 값=사용자 사전"** 형태로 확정. 1인용이므로 분류 기준의 소유자와 사용자가 동일하다는 점이 설계의 전제다.

**불변식 (이 체계의 안전장치):**
- PR·이력·진행 그래프는 지금처럼 **exercise_id 기준** — 속성은 절대 정체성이 아니다.
- 속성 수정은 계열 합산·필터 소속만 바꾸고, 해당 종목의 PR·세트 기록은 불변.
- 운영 규율(속성 수정 UI에 확인 문구로 노출): **"과거까지 사실이 바뀌는 '정정'이면 수정, 오늘부터 달라지는 '변경'이면 신규 등록."**

**스키마 (user_version 1→2 마이그레이션, 순수 additive ALTER):**

```sql
ALTER TABLE exercise ADD COLUMN base_movement TEXT;  -- 동작: "숄더프레스", "로우" 등
ALTER TABLE exercise ADD COLUMN equipment     TEXT;  -- 장비: "바벨", "덤벨", "케이블", "머신" 등
ALTER TABLE exercise ADD COLUMN support       TEXT;  -- 자세/지지: "시티드", "스탠딩", "체스트 서포티드" 등
ALTER TABLE exercise ADD COLUMN grip          TEXT;  -- 그립: "클로즈", "와이드", "뉴트럴" 등
ALTER TABLE exercise ADD COLUMN angle         TEXT;  -- 각도: "인클라인", "디클라인" 등
ALTER TABLE exercise ADD COLUMN aliases       TEXT;  -- 검색 별칭, 쉼표 구분: "숄더프레스,밀리터리 프레스"
```

- 전 컬럼 NULL 허용 자유 텍스트. **고정 enum·CHECK 없음** — 값은 사용자가 만들고, UI가 기존 값 자동완성으로 일관성을 돕는다. 조합 UNIQUE 제약 없음(같은 조합·다른 의도 허용, 중복은 경고로만).
- 시드 백필: **v1→v2 마이그레이션에서 1회만 실행** — 매 기동 실행이면 사용자가 속성을 전부 비운 내장 종목에 시드값이 되살아나므로 금지. 가드는 `is_builtin=1`이고 **속성 6컬럼 전부 NULL**인 행만 UPDATE(사용자 수정·'전부 비우기' 보존 — 원안 가드 `base_movement IS NULL`은 base가 NULL로 남는 백필 행(예: 슈러그)을 재덮어쓸 수 있어 그 부분집합인 전-6-NULL로 좁혔다. 2026-07-22 구현 결정). 신규 DB의 내장 종목 속성은 시드 INSERT가 직접 채운다. **명백한 것만 채운다**(장비·지지 위주) — 백필 시험에서 애매 판정된 종목은 NULL로 남긴다. 자의적 결정 금지. aliases는 통용 동의어가 확실한 것만(예: 오버헤드 프레스 ← "숄더프레스,밀리터리 프레스").

**하지 않는 것 (조사로 반증된 자동화):**
- 속성→부위 매핑 자동 유도 금지 (같은 '플라이'인 펙덱/리어델트가 부위 정반대 — 성립 안 함).
- 속성→bodyweight_factor·load_multiplier 유도 금지 (덤벨 벤치 ×2 vs 원암 덤벨 로우 ×1). 부위·계수는 기존대로 수동 입력, 복제 생성으로 완화.

**생성/수정 UI (Log의 NewExerciseForm·Exercises 폼 공통):**
1. 동작(base_movement) 자동완성 입력 → 속성 칩 4종(기존 값 자동완성 + 새 값 자유 입력, 전부 선택 사항).
2. **이름 자동 조합**: 어순 `그립 → 지지 → 각도 → 장비 → 동작` (예: "클로즈 그립 인클라인 바벨 벤치프레스"). 항상 수정 가능 — 자동명은 제안이지 강제가 아니다.
3. **분해 넛지**: base_movement를 지정했는데 support가 비어 있으면 "자세(시티드/스탠딩 등)를 지정할까요?" 1회 표시. 차단 아님 — 사용자의 '강제 분해' 습관을 돕는 장치.
4. **중복 경고**: 같은 5속성 조합의 활성 종목이 있으면 "같은 조합의 종목이 이미 있습니다: OOO" 경고 후 계속 진행 가능.
5. **복제 생성**: 기존 종목에서 "복제" → 폼에 속성·부위·계수 프리필 → 수정 후 저장 (변형 생성의 기본 경로).

**검색**: 종목 선택 bottom sheet·종목 관리 검색이 `name_ko / name_en / aliases / 속성값` 전부를 대상으로 매칭.

**분석 확장**: `GET /api/stats/family?base_movement=...` — 같은 base_movement 종목들의 날짜별 합산 볼륨 + 최고 e1RM + 참여 종목 목록. 참여 종목 목록은 활성 종목만, **볼륨 합산은 아카이브 종목의 과거 세트 포함**(분해 후 옛 통합 종목을 아카이브해도 계열 차트에서 과거 볼륨이 유지 — 다른 stats와 동일하게 set_volume 기반. 2026-07-22 구현 결정). 활성 참여 종목이 없으면 빈 결과(404 아님). Dashboard 종목 진행 드롭다운에 "OOO (계열)" 항목 추가 — **활성 2종 이상인 계열만 노출**(1종뿐이면 단일 종목 그래프와 동일하므로. 구현 결정). 분해로 갈라진 기록을 합쳐 보는 창구 — **분할의 비용을 상쇄하는 핵심 기능**. equipment/support 필터 집계는 v2.

**CSV export**: 기존 컬럼 뒤에 `base_movement, equipment, support, grip, angle` 추가.

**계약**: types.ts + 계약 테스트 동반 갱신 필수(기존 규칙). API의 Exercise 스키마에 6필드 추가(전부 optional).

### 3.7 기록 의도 주동근 + 이력 편집 확장 (2026-08-05 추가, 사용자 요청)

**A. 기록 의도 주동근 (intent)**

배경: 같은 종목도 수행 의도에 따라 목적이 다르다(데드리프트: 종합 스트랭스 vs 햄스트링 위주). 종목의 정적 부위 매핑에 더해, **기록 시점의 의도 주동근**을 선택적으로 저장한다.

- 스키마 (user_version 2→3): `ALTER TABLE workout_set ADD COLUMN intent_muscle_group_id INTEGER REFERENCES muscle_group(id);` — NULL(기본) = 종목 기본 매핑 사용. `set_volume` VIEW에 패스스루 추가(마이그레이션에서 DROP VIEW 후 재생성).
- **집계 규칙 (§6.1 부위 귀속의 확장, 단일 규칙)**: intent가 지정된 세트는 **intent 근육 1.0 + 그 종목 매핑의 나머지 근육 전부(원래 primary 포함, intent 제외) 0.5**. intent NULL이면 기존 규칙 그대로. intent가 종목 매핑에 없는 근육이어도 허용(사용자 의도 우선). **볼륨 총량·e1RM·PR은 무영향** — 부위 귀속과 부위별 세트 수만 바뀐다.
- API: `POST /api/sets`·`PATCH /api/sets/{id}`에 optional `intent_muscle`(muscle_group code, 예 "hamstrings", null 허용). 세트 응답 레코드에 `intent_muscle`·`intent_muscle_ko`(null 가능). CSV export 끝에 `intent_muscle` 컬럼 추가. stats의 부위 귀속 쿼리(summary muscle_sets / volume per_muscle·per_region / muscles) 전부 위 규칙 반영.
- UX (기록·세션상세 공통, §5.3 1탭 원칙 보존):
  - 활성 종목 카드에 소형 **"의도" 칩** (기본 표시 "기본"). 탭 → 12분류 근육 시트 → 선택 시 **이후 저장 세트에 자동 적용** (카드 단위 sticky). 이미 저장된 이 세션 같은 종목 세트가 있으면 "기존 N세트에도 적용할까요?" 확인.
  - **소급 적용 확인의 설정화 (2026-08-05 사용자 요청)**: 설정 화면에 "의도 변경 시 기존 세트" 3택 — **물어보기(기본) / 항상 적용 / 적용 안 함**. localStorage 저장(다른 설정과 동일 패턴). 확인 다이얼로그에 "다시 묻지 않기" 체크박스 — 체크 후 적용/적용 안 함을 선택하면 그 선택이 설정 기본값으로 저장된다.
  - 세션 간 carry-over 없음 — 새 세션은 항상 "기본"에서 시작.
  - 세트 인라인 수정에서 개별 세트의 intent 변경 가능. intent 지정 세트 행에는 근육명 소형 뱃지 표시.

**B. 이력 편집 확장**

- **세션 상세에 종목 추가**: Log의 종목 선택 bottom sheet를 공용 컴포넌트로 추출해 재사용. 추가된 종목의 세트는 해당 세션에 직접 귀속.
- **세트의 세션 직접 귀속**: `POST /api/sets`에 optional `session_id` 추가 — 지정 시 lazy 생성을 건너뛰고 그 세션에 직접 추가(세션의 date와 body date 불일치 시 422). 세션 상세의 "세트 추가"·"종목 추가"는 반드시 session_id를 지정한다. *(기존 결함 수정: date만으로 보내면 같은 날 두 번째 세션에 잘못 붙을 수 있었다.)*
- **빈 날짜에 과거 기록 생성**: History 캘린더에서 세션 없는 날짜 탭 → "이 날짜에 기록 추가" → `/history/new?date=YYYY-MM-DD` 편집 화면(세션 미생성 상태). 첫 세트 저장 시 `new_session=true`로 생성하고 반환된 session_id로 URL 교체 — **빈 세션을 만들지 않는 원칙(§4.2) 유지**.
- **세션 날짜·메모 수정 UI**: 세션 상세 헤더에서 진입(`PATCH /api/sessions/{id}` 기존 API). 날짜 변경 시 "주간 분석 소속이 바뀝니다" 확인 문구.
- 계약: types.ts + 계약 테스트 동반 갱신 (기존 규칙).

---

## 4. 백엔드 API

### 4.1 인증

**env 비밀번호 + JWT(HS256) Bearer, 만료 90일, refresh 없음.**

- 비밀번호: `APP_PASSWORD` env (`backend/.env`). `secrets.compare_digest`로 상수시간 비교. user 테이블 없음.
- 토큰: `POST /api/auth/login` 성공 시 PyJWT로 발급, 서명키 `JWT_SECRET` env, payload `{"exp": now + 90d}`.
- 만료 90일인 이유: 30일이면 만료 시점이 하필 운동 중일 때 세트 입력 직전 로그인 화면으로 튕긴다. 프론트는 앱 실행 시 남은 수명 7일 미만이면 재로그인 유도 배너를 띄운다.
- 보호 범위: `/api/auth/login`, `/health` 제외 전 엔드포인트 `Depends(require_auth)`.
- brute-force 완화: 로그인 실패 시 `asyncio.sleep(1)` 후 401. rate-limit 미들웨어는 미도입(단일 사용자 앱에 과함).
- 프론트 저장: `localStorage` + fetch 헤더 첨부, 401 시 `/login` 리다이렉트. (XSS 노출 리스크는 자체 제작 프론트 + 외부 스크립트 없음 + 개인 데이터 수준에서 **알고 수용하는 트레이드오프**로 명시.)

### 4.2 엔드포인트 전체 목록

#### Auth / Health

| Method | Path | 용도 |
|---|---|---|
| POST | `/api/auth/login` | `{password}` → `{access_token, token_type, expires_in}` |
| GET | `/health` | 배포 플랫폼 health check (인증 제외) |

#### Exercises

| Method | Path | 용도 |
|---|---|---|
| GET | `/api/exercises?include_archived=false` | 전체 목록. 각 항목에 `muscles:[{code, role}]`, `bodyweight_factor`, `load_multiplier`, `is_builtin`, `is_archived` |
| POST | `/api/exercises` | 추가. `{name_ko, name_en?, muscles(primary 1개 이상), bodyweight_factor=0, load_multiplier=1}`. 동명 아카이브 존재 시 복원 안내 응답: **409 + `detail={code:"archived_exists", exercise_id, name_ko}`** (types.ts `ArchivedConflictDetail`) |
| PATCH | `/api/exercises/{id}` | 수정 (builtin 포함) |
| DELETE | `/api/exercises/{id}` | 세트 있으면 archive, 없으면 hard delete. 응답 `{deleted, archived}` (types.ts `ExerciseDeleteResponse`) |
| POST | `/api/exercises/{id}/restore` | 아카이브 복원 |
| GET | `/api/exercises/{id}/last-record` | 지난 세션 같은 종목 기록 `{session_id, session_date, sets:[{weight_kg, reps, is_warmup}]}` — 입력 프리필의 핵심 |

#### Sets / Sessions / Bodyweight

| Method | Path | 용도 |
|---|---|---|
| POST | `/api/sets` | **세트 입력 — 가장 자주 호출.** `{client_id(UUID), date, exercise_id, weight_kg, reps, is_warmup?, new_session?}`. 세션은 lazy 생성: 해당 date의 가장 최근 세션에 붙이고, 없거나 `new_session=true`면 생성. `client_id` 중복이면 기존 행 200 반환(멱등). 응답에 `volume_kg, is_weight_pr, is_e1rm_pr` 포함 |
| PATCH | `/api/sets/{id}` | 오입력 정정 `{weight_kg?, reps?, is_warmup?}` |
| DELETE | `/api/sets/{id}` | 세트 삭제 |
| GET | `/api/sessions?from&to&limit&offset` | 세션 목록 (요약: `total_volume, exercise_count, set_count`) |
| GET | `/api/sessions/{id}` | 세션 상세 — 서버가 `exercise_id + min(set_index)` 순으로 종목별 그룹핑해 반환 |
| PATCH | `/api/sessions/{id}` | `{date?, note?}` |
| DELETE | `/api/sessions/{id}` | 세션 삭제 (sets cascade) |
| GET | `/api/bodyweight?limit` | 체중 이력 |
| POST | `/api/bodyweight` | `{date, weight_kg}` — date UNIQUE upsert |

- 세션 명시 생성 엔드포인트는 **두지 않는다** (빈 세션 잔존 방지, lazy 생성만).
- 실시간 PR 플래그는 **해당 종목에 이전 세션 기록이 있을 때만** 세운다 (첫 종목 첫 세션의 PR 뱃지 도배 방지).

#### Stats (분석 6종 — §6 카탈로그의 v1을 전부 커버)

| Method | Path | 반환 |
|---|---|---|
| GET | `/api/stats/summary` | 스탯 카드 일괄: 이번 주 볼륨(+전주 대비 %, 8주 스파크라인), 부위별 가중 세트 수, 최근 PR 3건, 빈도(주 운동일수·weekly streak·경과일), 누적(tonnage·세션·세트·reps) |
| GET | `/api/stats/volume?granularity=day\|week\|month&from&to` | 기간별 볼륨 추이. `points[].per_muscle`(12분류) + region 롤업 포함 |
| GET | `/api/stats/muscles?from&to` | 부위별 가중 볼륨·세트 수 분배 |
| GET | `/api/stats/exercises/{id}?from&to` | 종목별: 세션별 볼륨·top weight·e1RM 추이 + 현재 PR |
| GET | `/api/stats/prs` | 전 종목 PR 일람 + 최근 PR 피드 |
| GET | `/api/stats/calendar?months=6` | 일별 볼륨 (캘린더 히트맵용) |

응답은 차트에 바로 넣을 수 있는 `points` 배열 형태로 고정. **집계는 전부 서버 SQL** (원시 세트를 모바일로 내려 JS 집계하는 것은 트래픽·배터리·코드 중복 삼중 손해).

#### Export

| Method | Path | 용도 |
|---|---|---|
| GET | `/api/export/db` | `VACUUM INTO` 스냅샷 다운로드 (1차 백업 수단) |
| GET | `/api/export/csv` | 비정규화 플랫 CSV: `date, exercise_name_ko, name_en, set_index, weight_kg, reps, is_warmup, volume_kg, primary_muscles, note`. **UTF-8 with BOM** (Excel 한글 깨짐 방지) |

### 4.3 에러 처리·Validation

- Pydantic v2, request 스키마 `extra="forbid"` (필드 오타 422 조기 검출).
- 제약: `weight_kg: ge=0, le=500` + 0.25 배수 validator, `reps: ge=1, le=100`, `name: 1~50자 strip`, muscles는 primary·secondary 중복 금지 validator.
- 상태코드: 401(토큰), 404(id 없음), 409(이름 중복), 422(validation), 500(전역 handler에서 detail 마스킹, 스택은 로그만).
- 에러 포맷은 FastAPI 기본 `{"detail": ...}` 통일. 커스텀 envelope 없음.

### 4.4 backend/ 구조

```
backend/
├─ app/
│  ├─ main.py            # FastAPI 인스턴스, StaticFiles 마운트, startup에서 init_db+seed
│  ├─ config.py          # pydantic-settings: APP_PASSWORD, JWT_SECRET, DB_PATH, TOKEN_TTL_DAYS
│  ├─ auth.py            # login + require_auth dependency (PyJWT)
│  ├─ db.py              # sqlite3 연결 dependency (row_factory=Row, PRAGMA), DDL, VIEW
│  ├─ schemas.py         # Pydantic 스키마 전부 (한 파일)
│  ├─ seed_exercises.py  # §3.5 시드 (Python dict)
│  └─ routers/
│     ├─ exercises.py    # 종목 CRUD + restore + last-record
│     ├─ sessions.py     # sets + sessions + bodyweight
│     └─ stats.py        # 분석 6종 + export 2종
├─ tests/
├─ pyproject.toml        # uv. deps: fastapi, uvicorn[standard], pydantic-settings, PyJWT
├─ .env.example          # 키 이름만, 값 비움
└─ data/                 # 로컬 dev용 app.db (gitignore)
```

service layer·repository pattern·DI 컨테이너는 두지 않는다 — 라우터 함수 안 SQL 실행이 이 규모의 정답. 단일 사용자라 동시성 이슈는 사실상 없고, 안전망은 WAL만.

---

## 5. 프론트엔드 UI/UX

### 5.1 설계 원칙

- **엄지 존 우선**: 주요 액션은 화면 하단 1/3. 한 손 조작 전제.
- **타이핑 최소화**: 기본은 스테퍼(±)와 프리필. 숫자 키보드는 최후 수단.
- **프리필이 기본값**: 새 세트는 항상 값이 채워져 있다 → 같은 무게·횟수면 **탭 1회**로 세트 완료.
- 기록 화면에서 분석 요소 배제 (분석은 대시보드로).
- **다크 테마 단일** (헬스장 조명 눈부심 방지 + 테마 분기 코드 제거).
- 터치 타깃 최소 48×48px, `세트 완료` 버튼은 전폭×56px 이상.

### 5.2 라우트

| 라우트 | 화면 | 역할 |
|---|---|---|
| `/login` | 로그인 | 비밀번호 입력 → 토큰 저장, 이후 자동 로그인 |
| `/` → `/log` | 리다이렉트 | 기록이 홈 |
| `/log` | **운동 기록 (핵심)** | 앱 사용 시간의 90% |
| `/dashboard` | 대시보드 | §5.5 |
| `/history` | 기록 조회 | 캘린더(볼륨 농도 히트맵) / 리스트 토글 |
| `/history/:sessionId` | 세션 상세 | 열람·수정·삭제 |
| `/exercises` | 종목 관리 | 목록·추가·수정·숨김 |
| `/settings` | 설정 | §5.6 |

내비게이션: 하단 고정 탭바 `기록 | 분석 | 이력 | 종목`. 설정은 이력 화면 우상단 기어 아이콘.

### 5.3 운동 기록 화면 (`/log`)

입력 흐름과 탭 수:

| 시나리오 | 조작 | 탭 수 |
|---|---|---|
| 같은 무게·횟수 다음 세트 | `세트 완료` | **1** |
| 횟수 1 줄어든 세트 | `−` → `세트 완료` | 2 |
| 중량 2.5kg 올린 세트 | `+` → `세트 완료` | 2 |
| 새 종목 (최근 목록에 있음) | `＋종목 추가` → 칩 탭 → `세트 완료` | 3 |

핵심 규칙:
- 세션 "시작" 버튼 없음 — 첫 세트 저장 시 자동 생성 (서버 lazy 생성, §4.2). `세션 완료`는 클라이언트 활성 상태 초기화일 뿐 서버 상태 아님. 하루 2회 운동 분리는 명시적 `새 세션` 버튼으로.
- **하루 경계는 03:00** — 23:30에 시작한 운동이 자정에 두 세션으로 쪼개지지 않도록 클라이언트가 `date = (now − 3h)의 날짜`로 산출해 전송.
- 프리필 우선순위: ① 이 세션 같은 종목 직전 세트 → ② 지난 세션 같은 종목 마지막 세트(`last-record`) → ③ 빈 값.
- 중량 스테퍼 증분: 설정값 (1.25 / 2.5 / 5, 기본 2.5). 횟수 ±1. 숫자 직접 탭 → `<input inputmode="decimal">` 키패드 (드롭세트 등 큰 폭 변경).
- 스테퍼 옆 소형 `웜업` 토글 1개.
- 세트 완료 시: optimistic update 즉시 반영 + 백그라운드 POST (§5.4) + 휴식 카운트업 타이머 표시 (v1은 표시만 — 목표시간·알림·설정 없음, Phase 4).
- 세션 경과 시간 표시는 세트 `created_at`의 `min~max` 파생값.
- 완료된 세트 탭 → 인라인 수정/삭제.

와이어프레임 — 기록 메인:

```
┌──────────────────────────────────┐
│ 7/19 (토)               [세션 완료]│
│ 총 볼륨 4,320 kg · 52분           │
├──────────────────────────────────┤
│ ▸ 벤치프레스              3세트 ✓ │  ← 접힌 종목 카드 (탭=펼침·수정)
│   60×8 · 60×8 · 62.5×6           │
├──────────────────────────────────┤
│ ▾ 스쿼트                  (진행중)│  ← 활성 종목 카드
│  지난번 7/15 : 80×8 · 80×8 · 80×7 │  ← last-record
│  ① 80 kg × 8                      │
│  ② 80 kg × 8                      │
│  ┌─── 중량(kg) ───┬─── 횟수 ───┐ │
│  │  [−]  80  [+]  │ [−]  8  [+] │ │  ← 프리필 스테퍼 (□웜업)
│  └────────────────┴─────────────┘ │
│  ┌───────────────────────────────┐│
│  │        ✓  세트 완료  (3)      ││  ← 전폭 56px+, 엄지 존
│  └───────────────────────────────┘│
│   휴식  ⏱ 01:23                   │
├──────────────────────────────────┤
│         [ ＋ 종목 추가 ]          │
├──────────────────────────────────┤
│  ●기록   분석   이력   종목      │
└──────────────────────────────────┘
```

종목 선택 bottom sheet (`＋종목 추가`):

```
┌──────────────────────────────────┐
│  ══                          ✕   │
│  [🔍 종목 검색_______________]    │  ← 자동 포커스 X (탭해야 키보드)
│  최근 사용                        │  ← 최근 순 최대 8개 칩, 1탭 선택
│   스쿼트  벤치프레스  데드리프트   │
│  ────────────────────────────    │
│  가슴                            │  ← 부위별 그룹 리스트
│   벤치프레스              가슴/삼두│
│  ...                             │
│  [＋ 새 종목 만들기]              │  ← 검색 결과 없으면 상단 승격
└──────────────────────────────────┘
```

### 5.4 오프라인·재시도 설계 (헬스장 필수 — 별도 명세)

헬스장 네트워크는 끊긴다. TanStack Query 기본 retry만으로는 **유실**(메모리 큐 → 화면 꺼짐·탭 킬 시 소멸)과 **중복**(타임아웃 후 재전송 → 이중 기록) 둘 다 못 막는다.

1. 세트 저장 요청은 **localStorage outbox**에 먼저 기록 → 성공 시 제거. 앱 로드 시·`online` 이벤트 시 flush.
2. 각 세트는 클라이언트 생성 UUID `client_id`를 가지며 서버가 멱등 처리 (§4.2) → 재전송해도 중복 저장 없음.
3. 전송 대기 세트는 목록에 회색+스피너로 표기.
4. 앱 로드 시 항상 오늘 세션을 서버에서 재조회해 동기화 (탭 킬 후 재진입 복구).
5. 401 수신 시 outbox flush를 멈추고 큐 보존 → 재로그인 후 재개 (무한루프 방지).

### 5.5 대시보드 (`/dashboard`)

세로 스크롤 단일 컬럼 "지금 상태 → 추이 → 심층". 상단 기간 토글 `[주간|월간]`. PC는 `max-width: 720px` 중앙 컬럼.

| 순서 | 블록 | 차트 | 데이터 |
|---|---|---|---|
| 1 | 요약 스탯 (2×2) | 숫자 타일 | 이번 주 볼륨(전주 대비 %△+스파크라인), 세션 수, 세트 수, PR 수 — `/stats/summary` |
| 2 | 볼륨 추이 | bar (12주/12개월) | `/stats/volume` |
| 3 | 부위별 분배 | horizontal bar | 가중 볼륨 내림차순 — `/stats/muscles`. 도넛 대신 가로 막대 (길이 비교가 정확) |
| 4 | 부위 균형 추이 | stacked bar (주별) | `/stats/volume`의 per_muscle |
| 5 | 종목별 진행 | line + PR 표 | 종목 드롭다운(볼륨 상위순) → e1RM·top weight 추이 — `/stats/exercises/{id}` |
| 6 | 최근 PR 피드 | 리스트 | `/stats/prs` |

### 5.6 나머지 화면

- **이력**: 캘린더(기본) — 일별 볼륨을 단색 농도로 표시(잔디 스타일), 날짜 탭 → 세션 요약 카드 → 상세. 리스트 — 최신순 무한 스크롤. 세션 상세는 기록 화면과 같은 카드 레이아웃의 읽기 모드 + 수정 진입.
- **종목 관리**: 부위별 그룹 + 검색, 커스텀 뱃지, 우하단 FAB `＋`. 폼: 이름, **주동근 다중 선택(1개 이상)**, 보조근 다중 선택, 고급 항목으로 `bodyweight_factor`·`load_multiplier`(기본값 채움). 내장 종목도 수정 가능, 삭제는 숨김 처리.
- **설정**: 중량 스테퍼 증분(1.25/2.5/5) / 현재 체중 입력(+이력) / 데이터 내보내기(CSV·DB) / 로그아웃. ~~비밀번호 변경~~ 없음 — `APP_PASSWORD`는 env라 런타임 변경 불가, 변경은 `backend/.env` 수정 후 서버 재시작 (README에 기재).
- **체중 최초 입력 모달**: 체중 기록이 없는 상태에서 맨몸 종목(bodyweight_factor>0) 선택 시 1회 강제.

---

## 6. 분석 지표 명세

### 6.1 공통 정의

| 항목 | 확정 |
|---|---|
| 볼륨 | `set_volume` VIEW (§3.2·§3.3) — 맨몸 포함 단일 정의 |
| 기본 집계 대상 | `is_warmup=0`만. "웜업 포함" 스위치로 전환 가능 |
| 부위 귀속 | 볼륨·세트 수 모두 primary 1.0 / secondary 0.5 가중 (차트에 "가중" 명시) |
| e1RM | Epley, 웜업 제외, `1≤reps≤12`, weight>0, `weight_kg` 입력값 기준 |
| 주간 | **ISO-8601 월요일 시작.** 집계 키는 주 번호가 아니라 **그 주 월요일 날짜(`week_start`)** — 연말 경계 문제 해소, x축 라벨로 바로 사용. SQLite: `DATE(date, '-' \|\| ((CAST(STRFTIME('%w', date) AS INTEGER) + 6) % 7) \|\| ' days')` |
| 이번 주 | 진행 중 부분 주 — 전주 비교 카드에 "진행 중" 표시 |
| 월간 | 달력 월 `YYYY-MM` |
| 하루 경계 | 03:00 (§5.3) |
| 계산 방식 | **전 지표 read-only SQL 온디맨드. 사전 집계·캐시·PR 테이블 금지** — 1인 데이터(10년 4만 행)는 인덱스만으로 ms 응답, 파생 데이터가 없어야 수정·삭제 정합성이 공짜 |

### 6.2 지표 카탈로그 (v1 = 첫 완성품, v2 = 이후)

**A. 볼륨 추이** — v1: 기간별 총볼륨(일/주/월, bar·line), 주간 변화율(%카드), 주간 세트 수, 세션당 평균 볼륨. v2: 4주 이동평균 overlay, 급성:만성 볼륨 비율(>1.5 급증 경고).

**B. 부위별** — v1: 부위별 가중 볼륨 분배(horizontal bar), 부위별 주간 가중 세트 수. v2: 부위별 추이 multi-line, Push/Pull/Legs 밸런스, 방치 부위 감지(14일 무자극).

**C. 종목별** — v1: 세션별 볼륨 추이, top weight 진행(step line), e1RM 추이, 볼륨 Top 5 종목. v2: rep-max 매트릭스, 평균 강도(kg/rep), rep range 분포, 미수행 경과, 정체(plateau) 감지.

**D. PR** — v1: **Weight PR + e1RM PR 2종** (세트 저장 응답 플래그와 일치), 최근 PR 피드. v2: Rep PR(동일 중량 최다 reps), 단일 세트 Volume PR, 세션 Volume PR. *(4종 동시 v1은 과설계로 판정, 축소 확정)*

**E. 빈도·습관** — v1: 주당 세션 수, weekly streak(주 1회 이상 연속 주 수 — 일 단위 streak는 휴식일 때문에 무의미), 마지막 운동 후 경과일, 캘린더 히트맵. v2: 목표 달성 streak, 요일별 분포.

**F. 누적** — v1: 누적 tonnage, 총 세션/세트/reps.

### 6.3 PR 판정 규칙

- **저장하지 않고 조회 시 계산** (on-the-fly). 세트 수정·삭제 시 자동 반영 — 과거 세트를 지우면 그 PR도 자연 소멸.
- strictly greater(`>`)만 PR. 동률 아님.
- **첫 기록은 베이스라인** — 종목의 첫 세션은 PR 대상 제외 (실시간 뱃지도 "이전 세션 기록 존재 시"만).
- 같은 날 연속 갱신: 실시간 뱃지는 세트마다 / PR 히스토리는 **하루×종목×종류당 최고 1건만**.
- 종목 rename은 `exercise_id` 기준이라 무영향. 세트 있는 종목 hard delete 금지(archive만). 중복 생성으로 인한 히스토리 단절은 생성 폼의 유사 이름 경고로 예방, 병합은 v2.
- 맨몸(weight=0) 세트: Weight PR·e1RM 제외.

---

## 7. 배포·운영

### 7.1 호스팅: 연구실 PC 서버 + Tailscale Funnel — 0원 (2026-07-19 변경 확정)

**24시간 켜져 있는 연구실 Windows PC**(사용자 확인)에서 서버를 상시 실행하고, **Tailscale Funnel**로 고정 공개 URL을 발급받아 헬스장 LTE에서도 접속한다. 상시 구동이 보장되므로 절전·전기료 문제는 없다.

Funnel 사실 확인 (2026-07 웹 검색, 출처는 공식 문서):
- **전 플랜 무료**, 자기 도메인 불필요 — 고정 URL `https://<pc이름>.<tailnet>.ts.net`, HTTPS 인증서 자동.
- Windows CLI 지원. 설정은 사실상 **`tailscale funnel --bg 8000` 1개 명령** + 브라우저 승인 1회 (요건: MagicDNS·HTTPS 활성화 — 첫 실행 프롬프트로 처리).
- 무료 플랜 한도 6 users (2026-04 pricing v4 기준) — 1인 사용에 무관.
- bandwidth 제한 존재(수치 비공개) — 소량 JSON API라 무관.
- **아웃바운드 터널이므로 공유기 포트포워딩·인바운드 방화벽 개방 불필요.**

검토했던 대안:
- **Cloudflare Tunnel**: named tunnel의 고정 hostname은 **Cloudflare에 등록된 자기 도메인 필수**(공식 문서 확인) → 도메인 구매(연 1~2만원) 없이는 불가. Quick Tunnel(trycloudflare.com)은 실행마다 URL이 바뀌는 테스트 전용. 탈락.
- **ngrok free**: 고정 dev domain 1개 무료지만 월 1GB/20k req 제한 + 브라우저 경고 페이지. Funnel 열위.
- **보안 최상 변형**: Funnel(전체 인터넷 공개) 대신 폰에도 Tailscale 앱을 설치해 tailnet 내부로만 접속(공개 노출 0). 폰에 VPN 상시 켜기가 괜찮다면 이쪽이 더 안전 — v1은 브라우저만으로 되는 Funnel 채택, 언제든 전환 가능.

> **정직 고지 — 이 구성의 대가**:
> 1. **재부팅·윈도우 업데이트 순간엔 헬스장에서 앱이 안 열린다.** outbox(§5.4)는 "이미 열려 있는 앱"의 전송 실패만 구제하고, 앱 로드 자체는 못 구제한다 — 그 순간의 기록은 폰 메모 후 나중 입력. 자동 시작 등록(아래)으로 다운타임을 재부팅 몇 분으로 최소화.
> 2. **기관 네트워크 변수**: 연구실 방화벽·보안 정책에 따라 Tailscale 설치나 터널 연결이 막힐 수 있다. Tailscale은 아웃바운드 연결(NAT 통과 + DERP relay fallback)이라 대부분 통과하지만 보장은 아님 — **Phase 0에서 `tailscale funnel` 동작을 폰 LTE로 먼저 확인**하고, 막히면 §7.5로 전환. 개인 서버 운용이 기관 정책상 허용되는지도 사용자가 확인할 것.
> 3. Tailscale 무료 정책 변경 리스크 — 유사시 §7.5 유료 전환 경로로 이동.

운영 설정 (Phase 2에서 스크립트로 자동화):
- 서버 자동 시작: Task Scheduler에 "시스템 시작 시" `scripts/start-server.ps1` 등록 (`scripts/register-startup.ps1`이 등록을 수행).
- Tailscale 서비스는 설치 시 자동 시작이며 `funnel --bg`는 재부팅 후에도 유지되는지 설정 시점에 확인, 아니면 start-server.ps1에 포함.
- 전원 옵션: 시스템 절전이 꺼져 있는지 1회 점검 (24시간 구동 중인 연구실 PC라 이미 충족일 가능성 높음).

### 7.2 저장소 구조 (모노레포, GitHub private)

```
파이썬_볼륨트레이닝_어플/
├─ backend/               # §4.4
├─ frontend/
│  ├─ src/
│  ├─ index.html
│  ├─ vite.config.ts      # server.proxy: { "/api": "http://localhost:8000" }
│  └─ package.json
├─ scripts/
│  ├─ start-server.ps1      # frontend build + uvicorn 운영 기동 (+funnel 확인)
│  ├─ register-startup.ps1  # Task Scheduler 등록 (시스템 시작 시 start-server)
│  └─ backup.ps1            # VACUUM INTO 스냅샷 → 클라우드 드라이브 폴더 (§7.4)
├─ .env.example           # 키 이름만 커밋
├─ .gitignore             # .env, backend/data/, node_modules, dist, .venv
├─ SETTING.MD             # 이 문서
└─ README.md
```

- secret은 `backend/.env` 한 곳 (`APP_PASSWORD`, `JWT_SECRET`, `DB_PATH`). Docker·클라우드 secret 주입 없음 — 구성이 단순해졌다.
- frontend에 비밀값 금지 (`VITE_*`는 번들에 노출됨).

### 7.3 개발·운영 흐름 (Windows 11 + PowerShell)

개발 (핫리로드):

```powershell
# 터미널 1 — 백엔드
cd backend; uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 터미널 2 — 프론트
cd frontend; npm install
npm run dev -- --host    # 0.0.0.0 바인딩 → 폰 접속 허용
```

**폰 테스트 (Phase 0부터 상시)**: 같은 Wi-Fi → `ipconfig`로 PC IPv4 확인 → 폰 브라우저 `http://<PC_IP>:5173`. 안 열리면 (관리자 1회):

```powershell
New-NetFirewallRule -DisplayName "vite-dev" -Direction Inbound -Protocol TCP -LocalPort 5173,8000 -Action Allow -Profile Private
```

네트워크 프로필이 "공용"이면 규칙이 안 먹으므로 해당 Wi-Fi를 "개인"으로 변경. (이 방화벽 규칙은 로컬 dev 전용 — Funnel 운영에는 인바운드 개방이 필요 없다.)

운영 (상시 서버, `scripts/start-server.ps1` 하나로):

```powershell
cd frontend; npm run build          # dist/ 생성 → FastAPI가 서빙
cd ..\backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000   # --reload 없이
tailscale funnel --bg 8000          # 최초 1회 승인 후 상시 유지
```

코드 수정 반영 = build + 서버 재시작 (start-server.ps1 재실행). 접속 주소는 항상 `https://<pc이름>.<tailnet>.ts.net`.

### 7.4 백업 (PC 디스크가 원본 — 오프사이트 1겹 필수)

| 층 | 수단 | 주기 |
|---|---|---|
| 1 | **서버 내장 자동 백업** (`app/backup.py`, 2026-07-20 추가): 쓰기 API 성공을 감지해 마지막 기록 후 5분 조용하면(=운동 종료) `VACUUM INTO` 스냅샷 → `BACKUP_DIR`(.env, OneDrive 동기화 폴더). 기록이 계속돼도 30분마다 강제 1회. 실패 시 30초 주기 재시도 | 데이터 변경 시 즉시(디바운스) |
| 2 | `scripts/backup.ps1` (Task Scheduler 등록) — 1층과 같은 폴더·파일명 규칙, 서버가 죽어 있어도 도는 보조 안전망 | 매일 1회 |
| 3 | `GET /api/export/db` 수동 다운로드 버튼 (폰에서도 가능) | 수시 |
| 4 | (v2) Litestream → Cloudflare R2 실시간 복제 — 세트 단위 유실까지 막고 싶어지면 | 실시간 |

- 스냅샷은 날짜 파일명(`app-YYYYMMDD.db`)으로 최근 30개 보존, 이전 것 자동 삭제.
- 복구 절차 README 명문화 + **Phase 2 완료 시 복구 리허설 1회 실제 수행** (해보지 않은 백업은 백업이 아니다).

### 7.5 유료 전환 경로 (보관용 메모)

연구실 PC를 쓸 수 없게 되거나(졸업·자리 이동 등) 기관 정책에 터널이 막히면: **Fly.io 도쿄 `nrt` 유료** (`shared-cpu-1x` 256MB ~$2.02/월 + volume 1GB $0.15/월, `min_machines_running=1`로 sleep 없음, 한국 왕복 30~40ms) + Litestream→R2. 2026-07 조사 기준 무료 클라우드 중 "cold start 없음 + 영속 디스크"를 만족하는 곳은 없었다 (Render free: sleep+ephemeral, Koyeb free: scale-to-zero 강제, Oracle Always Free: 진짜 VM이지만 2026-06 할당 무공지 축소 전례 + 직접 운영 부담).

---

## 8. 개발 로드맵

**외부 공개(Phase 2)를 분석(Phase 3)보다 앞에 둔다** — 분석은 데이터가 쌓여야 의미가 있으므로, 기록이 되는 즉시 헬스장에서 쓸 수 있게 만들어 실사용 데이터 축적을 시작한다.

| Phase | 내용 | 완료 기준 |
|---|---|---|
| **0. 스캐폴드** (반나절) | 모노레포 생성, backend(uv+FastAPI hello)·frontend(Vite React) 부팅, proxy 연결 | 폰(로컬 Wi-Fi)에서 dev 화면이 열린다 |
| **1. 기록+조회 (로컬)** | 스키마+시드, 세트/세션/종목/체중 API, 기록 화면(프리필·스테퍼·웜업 토글·bottom sheet), 이력 조회 | **실제 운동 1회를 폰으로 처음부터 끝까지 기록**하고 다음 날 조회된다 |
| **2. 외부 공개+인증+오프라인** | JWT 로그인, 전 API 가드, outbox+멱등(§5.4), 운영 스크립트(start-server·register-startup·backup)+Task Scheduler, Tailscale Funnel 설정, **복구 리허설** | 헬스장 LTE에서 기록이 되고, PC 재부팅 후 서버·터널·백업이 자동 복구된다 |
| **3. 분석 대시보드** | `/stats` 6종 SQL 집계 + 대시보드 6블록 + 캘린더 히트맵 (§6 v1 전부) | 실데이터로 전 지표가 렌더링된다 |
| **4. 다듬기 (선택)** | 휴식 타이머 목표시간·설정, Rep/Volume PR, rep-max 매트릭스, 캘린더 부위색, 종목 병합, RPE 입력, CSV 자동 백업 | — |

---

## 9. 알고 수용하는 트레이드오프

1. **서버가 연구실 PC** — 재부팅·윈도우 업데이트 순간의 짧은 다운타임(그 순간 기록은 폰 메모), 기관 네트워크 정책에 터널이 막힐 가능성(Phase 0에서 확인), 연구실을 떠나면 서버도 함께 사라짐. 유사시 §7.5 유료 클라우드(월 ~$3) 전환.
2. **무료 터널(Tailscale) 정책 변경 리스크** — 2026-07 현재 무료 확인됨, 변경 시 §7.5로 이동.
3. **localStorage JWT는 XSS에 이론상 노출** — 자체 프론트 + 외부 스크립트 없음 + 개인 데이터 수준에서 수용.
4. **bodyweight_factor는 근사값** — 목적은 정밀 역학이 아니라 맨몸 볼륨 0 왜곡 방지.
5. **부위별 가중 볼륨의 합 ≠ 총볼륨** (secondary 0.5 가중) — 차트에 "가중" 명시로 해소.
6. **시간 기반 운동(플랭크) 미지원** — v1 스코프 제외, 필요 시 별도 컬럼으로 추가.

---

## 10. v2 개정 (2026-09-08) — 다중 사용자 · 타겟 부위 · 종목 라이브러리

사용자 문답(2026-09-08)으로 확정. 이 섹션이 §1·§3·§4·§5·§6의 해당 항목보다 우선한다. 구현·마이그레이션은 같은 날 완료(스키마 v4).

### 10.0 결정 요약

| 항목 | 결정 |
|---|---|
| 사용자 | **다중 사용자** (본인 + 지인). 아이디/비밀번호 가입·로그인. 다른 플랫폼 연동은 이후 |
| 보안 수준 | 최소 — 무차별 대입 지연·잠금·이메일 인증 없음 (사용자 결정: 지인 전용). 비밀번호는 표준 라이브러리 scrypt 해시만 (비용 0) |
| 관리자 | **읽기 전용** — 사용자 목록·각 사용자의 기록 열람만. 시스템 수정은 작업 PC에서 직접 |
| 부위 귀속 | **세트 볼륨은 그 세트의 타겟 부위에 100%**. 협응근 분배 없음 (계산 단순함 우선, "일단은 이렇게") |
| 타겟 분류 | 부위 6 → 근육 14 → 세부 43의 3단계. 어느 단계에서 골라도 됨. 사용자가 세부 목록을 직접 보완 |
| 분할 루틴 | 분할표를 두지 않는다. 세션 부위 라벨은 그날 세트 타겟에서 자동 도출 (분할 방식은 사람·시기마다 다름) |
| 종목 속성 | **계열(base_movement)만 전용 필드**, 장비·자세·그립·각도는 자유 **태그**. **이름 자동 조합 폐기** ("스탠딩 케이블 트라이셉스 푸시다운" 문제) |
| 종목 라이브러리 | 고급자 기준 변형 포함 **내장 391종**을 미리 넣고 사용자는 **즐겨찾기**로 자주 쓰는 종목만 고른다. 종목 추가 기능은 남기되 주 경로가 아님 |
| 머신 | 브랜드·모델 카탈로그(395대 초안)를 종목에 선택적으로 연결. 연식별 타겟 차이는 앱이 알 필요 없음 — 타겟은 기록 시 세트 단위로 고른다 |
| 기존 기록 | 커스텀 19종을 라이브러리 이름으로 병합/승격 (매핑표 `db.CUSTOM_MERGE_MAP`), 세트는 종목 기본 타겟으로 채움 |

### 10.1 계정·인증

- `user(id, username UNIQUE, password_hash, display_name, is_admin, created_at)`. `username`은 영문·숫자·`._-` 2~32자, 비밀번호 4자 이상.
- `POST /api/auth/register {username, password, display_name?}` → 201 + 토큰(가입 즉시 로그인). `POST /api/auth/login {username, password}`. `GET /api/auth/me`. `POST /api/auth/password {current_password, new_password}` → 204.
- JWT payload `{sub: user_id, exp}`. v1 토큰(sub 없음)은 401 → 재로그인 (배포 후 1회).
- **첫 관리자**: 사용자 테이블이 비어 있을 때 마이그레이션이 `.env`의 `ADMIN_USERNAME`(기본 admin)·`APP_PASSWORD`로 생성. 이후 `.env` 값은 쓰이지 않는다 (비밀번호는 앱에서 변경). 가입으로 만든 계정은 항상 일반 사용자.
- 모든 데이터 조회·변경은 로그인한 사용자 범위로 제한: 세션·세트·체중·즐겨찾기·커스텀 종목·통계·CSV. `client_id` 멱등 키도 사용자 범위(전역 UNIQUE와 충돌 시 409).
- 운영 고지: 지인 데이터가 연구실 PC의 공개 URL로 노출된다. §9의 트레이드오프(재부팅 다운타임, XSS 시 토큰 노출)가 남의 데이터에도 적용됨을 알고 수용.

### 10.2 타겟 부위 체계

- `muscle_group`에 `level(2|3)`·`parent_id` 추가. level 2 = 근육(기존 12 코드 유지 + `adductors`·`hip_flexors`), level 3 = 세부(`upper_chest`, `vastus_medialis`, `triceps_long` …, `seed_data/targets.py`). `region` 컬럼은 부위 6분류(가상 상위 단계). `target_path` VIEW가 타겟 → 근육 → 부위 경로를 준다.
- `workout_set.target_id`(옛 `intent_muscle_group_id`를 RENAME). **앱이 항상 채운다**: 저장 시 미지정이면 종목 `default_target_id`. 응답 `target`·`target_ko`는 null 아님. PATCH `target: null` = 종목 기본으로 복귀.
- `exercise_muscle`(주동근/보조근) 삭제 → `exercise.default_target_id` 하나.
- **집계 단일 규칙**: 세트 볼륨·세트 수는 `target_id`에 100%. 세부 타겟은 근육·부위로 자동 합산. `set_volume`·PR·e1RM·총볼륨은 무영향.
- 분석: `per_muscle`은 근육(level 2) 코드 키, `/api/stats/muscles`는 타겟 행 전부(level 2 = 자기+세부 합, level 3 = 자기). 대시보드 "부위별 분배"는 부위/근육/세부 토글 드릴다운. `muscle_sets_this_week`는 근육 단위 `set_count`(정수).
- **세션 부위 라벨**: 세트 타겟을 부위로 합산해 1위가 `main_region`, 2위가 세션 볼륨의 **25% 이상**이면 `region_label`에 "하체·등"으로 함께. 동률은 고정 부위 순서. 25%는 추정치 — 써 보고 조정(`routers/sessions.SECOND_REGION_MIN_SHARE`).
- UX: 기록·세션 상세의 종목 카드 "타겟" 칩(종목 기본이 미리 선택, 다르면 accent 강조) → 3단계 시트. 카드 단위 sticky, 세션 간 carry-over 없음(§3.7A 규칙 유지). 소급 적용은 설정 3택(물어보기/항상/안 함) 그대로. 세트 행 뱃지는 **종목 기본과 다른 타겟만** 표시.
- `GET /api/targets` — 분류는 데이터. 프론트는 코드를 하드코딩하지 않고 여기서 받아 캐시.

### 10.3 종목 라이브러리 · 계열 · 태그 · 즐겨찾기

- `exercise`: `base_movement`(계열, 전용 필드 유지) + `tags`(쉼표 구분 자유 태그, 옛 equipment/support/grip/angle 4컬럼은 tags로 흡수 후 DROP) + `default_target_id` + `machine_id` + `user_id`(NULL = 내장 공용, 값 = 소유자) + `aliases`.
- **내장 라이브러리** `seed_data/exercises.py` 391종 (v1 45종 이름·계수 그대로 포함). 기동 시 name_ko 기준 INSERT OR IGNORE. 데이터 파일이라 사용자가 자유롭게 고쳐도 된다(코드가 아님). 시간 기반 종목 제외, 어시스티드 풀업·딥스는 체중 계수 0.5 근사(음수 중량 입력 불가).
- 이름은 통용명 그대로. **이름 자동 조합·분해 넛지·중복 조합 경고·정정/변경 확인 다이얼로그 폐기**. 계열 합산(`/api/stats/family`)은 유지 — 그래서 계열만 전용 필드.
- 가시성·권한: 내장은 모두에게, 커스텀은 소유자에게만. **내장 수정·숨김은 관리자만**(403), 일반 사용자는 **복제**해서 내 종목으로. 커스텀 삭제는 소유자만. `name_ko`는 전역 UNIQUE 유지(다른 사용자의 커스텀과 이름이 겹치면 409 — 지인 규모에서 수용).
- **즐겨찾기** `favorite(user_id, exercise_id, sort_order)`: `GET/PUT /api/favorites`, `POST/DELETE /api/favorites/{id}`. 종목 선택 시트 최상단(순서 편집은 종목 화면). 마이그레이션이 기존 사용자의 세트 수 상위 15종으로 초기화.
- 종목 선택 시트: 즐겨찾기 → 최근 사용 → 검색(이름·별칭·태그·계열·머신) / 부위별 펼치기. 전체 목록은 검색·펼치기로만 연다(수백 종 스크롤 방지).
- 검색·자동완성 소스는 이미 로드된 종목 목록의 distinct 값(계열·태그) — 사용자 사전 원칙 유지.

### 10.4 머신 카탈로그

- `machine(id, brand, model UNIQUE(brand, model), name_ko, target_id?)`. `seed_data/machines.py` 초안 395대(2026-09-08: Hammer Strength 81, gym80 76, Life Fitness 70, 뉴텍 64, Nautilus 61, Arsenal Strength 43) → **2026-09-14 확장 1,735대, 9개 브랜드**: Hammer Strength 133, gym80 187, Life Fitness 178, 뉴텍 139, Nautilus 245, Arsenal Strength 93, **Cybex 262, Panatta 346, 렉스코 152**(신규 브랜드). 1차 조사에서 브랜드당 ~150 상한(내 임의 기준)으로 뺐던 단종 라인은 사용자 확인 후 2차 조사로 추가(Nautilus XPLoad·NOVA·2ST·F3, Cybex VR2·VR·VR Classic·VR3 Total Access·5000·Modular, Panatta Fit Evo·Freeweight One·The Original·Fantastic·Powerlifting). 어린이용(Panatta Kids 4종) 제외. 출처 없이 이름만 아는 구형(Hammer 구 Iso-Lateral, gym80 이전 세대 등)은 넣지 않는다 — 마주치면 앱에서 직접 추가. 브랜드별 공식 카탈로그 전수 조사(에이전트 9개 병렬, 항목마다 출처 URL 확보; Panatta만 공식 사이트 차단으로 공식 디스트리뷰터·2017 공식 PDF). 단종 모델 포함, 플랫폼·랙 액세서리·덤벨/원판 랙 제외. 모델명은 제조사 표기, `target_id`는 참고값.
- 시드 규칙: 기동 시 `(brand, model)` INSERT OR IGNORE → 파일에 행을 **추가**하면 재시작만으로 DB에 반영된다. 기존 튜플의 문자열 변경·삭제는 DB에 전파되지 않으므로(변경은 중복행) 하지 않는다. 원 시드에 같은 기계가 두 이름으로 든 사례(Life Fitness `Plate Loaded Shoulder Press` = `Signature Series Plate Loaded Shoulder Press`)는 알고 둔다.
- 알려진 한계: 한 기계가 라인 이동으로 두 번 들어갔을 가능성(뉴텍 Torque/ON HIM 리버스 하이퍼), Cybex는 lifefitness.com에서 전 제품 '단종' 표시(현행 생산 미확인).
- **아카이브 + 내 머신 (2026-09-14 사용자 결정, 스키마 v6)**: 카탈로그는 아카이브로 계속 키우되(단종 포함), 사용자는 자기 헬스장에 있는 머신만 검색해 **내 머신**에 담는다. 종목 폼의 머신 칸에는 내 머신 칩만 보이고 아카이브는 검색 시트로만 연다 — "운동할 때마다 종목 추가에 몇천 개가 뜨면 곤란".
  - `user_machine(user_id, machine_id, created_at, PK(user_id, machine_id))`. v5→v6 데이터 단계: 커스텀 종목에 이미 연결된 머신을 소유자의 내 머신으로 1회 등록.
  - `GET /api/machines?q=&brand=&limit=`(공백 토큰 AND, 브랜드·모델·한글 별칭, 대소문자 무시, 파라미터 없으면 전체), `GET /api/machines/brands`(브랜드별 대수), `GET/POST/DELETE /api/me/machines[/{id}]`(최근 담은 순). `POST /api/machines` 직접 추가는 추가한 사람의 내 머신에 자동 등록.
  - 화면: 종목 폼 `MachineField`(없음 / 내 머신 칩 / ＋ 검색해서 추가), `MachinePicker` 시트(브랜드 칩 + 검색, 상위 60개, 직접 추가 폼), 설정 "내 머신"(목록·빼기·검색해 담기). 편집 중인 종목의 머신이 내 목록에 없어도 `machine_label`로 칩을 보여 준다.
  - 헬스장 단위 관리는 이번엔 없음 — 필요해지면 내 머신에 헬스장 태그를 붙인다.
- `GET /api/machines`, `POST /api/machines`(누구나 추가, 공용). 종목 폼의 선택 항목. 연식별 타겟 차이는 기록 시 타겟 선택으로 흡수.

### 10.5 관리자 페이지 (읽기 전용)

- `is_admin` 계정에만 "관리" 탭. `GET /api/admin/users`(세션·세트 수·마지막 날짜), `GET /api/admin/users/{id}/sessions`, `.../sessions/{sid}`, `.../bodyweight`. 쓰기 경로 없음.
- `GET /api/export/db`(전체 스냅샷)는 관리자만. CSV는 본인 데이터만.

### 10.6 스키마 v4 · 마이그레이션 · 병합

- `PRAGMA user_version` 3 → 4. 구조 단계(`db._migrate_structure`, 컬럼 존재 확인 기반 멱등) → VIEW 재생성(`set_volume`에 `user_id`·`target_id`, 체중 조회는 세션 소유자 기준 / `target_path`) → 시드 → 데이터 단계(`db._apply_v4_data`) → 버전 기록, 한 트랜잭션.
- 데이터 단계: 첫 관리자 생성 → 소유자 없는 세션·체중·커스텀을 관리자에 귀속 → 내장 종목 기본 타겟·계열·태그·별칭을 시드로 채움(default_target 비어 있는 행만) → 커스텀 기본 타겟 = 옛 주동근 첫 번째 → 세트 `target_id` 비어 있으면 종목 기본 → `exercise_muscle` DROP → **커스텀 병합**(정규화 이름 일치 또는 `CUSTOM_MERGE_MAP`: 내장 행이 따로 있으면 세트를 옮기고 삭제, 이름이 라이브러리와 같아 시드가 무시된 행은 내장으로 **승격**해 id·기록 보존) → 즐겨찾기 초기화.
- `body_weight_log`는 UNIQUE(date) → UNIQUE(user_id, date)로 재구축. `workout_session.user_id` 인덱스.
- 실사용 DB(세션 17·세트 311·커스텀 19) 사본으로 검증: 16종 병합/승격, 3종 유지(암풀다운·시티드 디클라인 체스트 프레스 머신은 매핑 추가 후 병합, 케이블 트라이셉스 프레스는 판단 보류로 유지). 총볼륨 +3,075kg — 푸쉬업 5세트가 내장 푸시업(체중 계수 0.65)으로 합쳐지며 체중이 포함됐고, 인클라인 덤벨 플라이 1세트가 ×2 규칙을 받은 결과. 볼륨 규칙(§3.3)대로이며 의도된 변화.

### 10.7 API 변경 요약

- 추가: `/api/auth/register`, `/api/auth/me`, `/api/auth/password`, `/api/targets`, `/api/machines`, `/api/favorites`, `/api/admin/*`.
- 변경: 세트 `intent_muscle` → `target`(응답 `target`·`target_ko` 필수), 세션 요약 `region_label` 추가·`main_region` 유지, 세션 그룹 `default_target`, 종목 `muscles` 제거 → `tags[]`·`default_target`·`default_target_ko`·`machine_id`·`machine_name`·`is_own`, stats `muscle_sets_this_week[].set_count`, `MusclePoint`에 `level`·`parent_code`, CSV 컬럼(타겟 3단계·태그·머신).
- 계약: types.ts + 계약 테스트 동반 갱신 규칙 유지 (pytest 140).

### 10.8 파일 구조 추가 (§4.4 보완)

```
backend/app/
├─ seed.py                # 시드 삽입 로직 (옛 seed_exercises.py)
├─ seed_data/             # 데이터: targets.py(분류) · exercises.py(라이브러리 391) · machines.py(카탈로그 395)
└─ routers/catalog.py     # targets · machines
   routers/admin.py       # 읽기 전용 관리자
frontend/src/
├─ hooks/                 # useTargets · useMe · useFavorites
├─ components/target/     # TargetChipButton · TargetSheet · TargetBackfillModal · useTargetBackfill
└─ pages/Register.tsx · pages/Admin.tsx
```

### 10.9 알고 수용하는 것 · 미결

1. 협응근 볼륨을 세지 않으므로 "부위별 분배"는 관여 근육이 아니라 **의도한 부위**의 분포다 (차트 문구로 표시).
2. `name_ko` 전역 UNIQUE — 서로 다른 사용자가 같은 이름의 커스텀을 만들 수 없다. 지인 규모에서 수용.
3. 라이브러리·타겟 세부·머신 카탈로그는 초안. 정확성 검토는 사용자 몫. 코드가 아니라 데이터라 수정이 곧 반영된다(다음 기동 시 INSERT OR IGNORE — 이름을 바꾸면 새 행이 생기니 기존 행은 앱에서 수정).
4. 세션 부위 라벨 2위 임계 25%는 추정치.
5. 다른 플랫폼 연동(소셜 로그인), 사용자별 분할 루틴 저장은 이후.

---

## 11. v2.1 개정 (2026-09-10) — 고급 분석 묶음 · 간접 볼륨 · 데이터 준비도 게이트

사용자 문답(2026-09-10)으로 확정: "묶어서 한번에 진행하되 4주 이하의 데이터로는 고급 분석에 접근할 수 없도록 락". §6.2의 v2 항목 중 아래 6종을 구현한다. **§10.2의 귀속 규칙(세트 볼륨은 타겟에 100%)은 그대로 정본**이며, 간접 볼륨은 그 옆에 붙는 보조 데이터다.

### 11.0 결정 요약

| 항목 | 결정 |
|---|---|
| 게이트 규칙 | **훈련 주**(웜업 아닌 세트가 하나라도 있는 ISO 월요일 시작 주)가 **4주 이상**이면 열림. 달력 경과·세션 수가 아니라 실제 기록된 주. 사용자별 계산, 관리자도 자기 데이터 기준. 상수 `routers/stats.ADVANCED_MIN_WEEKS` |
| 게이트 성격 | 역할 권한(관리자/일반)이 아니라 **데이터 준비도** 게이트. 구현 계층은 권한과 같다 — `require_analytics_ready` 의존성이 고급 라우터 전체에 걸려 URL 직접 호출로 우회 불가. 4주 미만이면 이동평균·ACWR·빈도 평균이 잡음이라 막는다 |
| 잠금 응답 | `403 {detail: {code: "insufficient_data", weeks_of_data, required_weeks}}`. `/api/stats/summary.analytics {ready, weeks_of_data, required_weeks}`가 상태를 미리 알려 프론트가 잠금 카드(진행 n/4주)를 보여 준다 |
| 잠금 대상 | 신규 고급 분석 6종만. 기존 대시보드(볼륨·부위별 분배·PR·종목 진행·계열)는 그대로 |
| "4주 이하" 해석 | 글자대로면 5주부터 열리지만, 4주 이동평균이 성립하는 최소 길이가 4주라 **4주에서 연다**. 상수 하나로 조정 |
| 간접 볼륨 방식 | fractional set counting (Baz-Valle 2021, RP의 "간접 세트"). 직접 1.0 + 간접 × 가중치(기본 0.5, 설정에서 ⅓ 선택). **총볼륨·PR·부위별 분배·세션 라벨에는 절대 미포함** — 고급 분석의 '관여 근육 분배' 카드에서만 |
| 보조 근육 데이터 | `seed_data/secondary.py` 391종 초안(267종에 보조 근육, ≤3개). 검토는 사용자 몫. 종목 폼에서 편집(내장은 관리자만) |

### 11.1 데이터 준비도 게이트

- 훈련 주 수 = `COUNT(DISTINCT week_start) FROM set_volume WHERE user_id = ? AND is_warmup = 0` (`routers/stats.training_weeks`). 같은 주의 세션 여러 개는 1주, 웜업만 있는 주는 0.
- `routers/analytics.require_analytics_ready` = `require_auth` + 위 계산. 라우터(`/api/stats/advanced/*`) 수준 의존성 — 핸들러가 빠뜨릴 수 없다.
- 프론트: 요약 응답의 `analytics.ready`로 섹션 전체를 잠금 카드 하나로 대체. 열린 뒤 어떤 카드가 403을 받으면(기록 삭제로 4주 미만이 된 경우) 그 카드만 잠금 문구.
- 관리자 페이지는 다른 사용자의 분석을 보여 주지 않으므로 게이트와 무관.

### 11.2 직접/간접 이중 집계 (스키마 v5)

- `exercise_secondary_target(exercise_id, target_id)` — 종목의 보조(협응) 근육. 기본 타겟은 넣지 않는다 (VIEW가 합친다). API `secondary_targets[]`(≤5, 기본 타겟과 같으면 422, 기본 타겟을 보조 중 하나로 바꾸면 그 보조는 자동 제거).
- `set_indirect` VIEW: 세트 × 간접 후보 근육. 후보 = 보조 근육 ∪ 종목 기본 타겟, 단 **세트 타겟과 같은 근육(level 2)이면 제외**, 근육 단위 DISTINCT. 그래서 (a) 기본 타겟대로 기록한 세트는 보조 근육만 간접, (b) 타겟을 바꿔 기록한 세트(벤치를 삼두로)는 기본 타겟(가슴)도 간접이 되고 삼두는 직접만, (c) 세부 타겟(상부 가슴)은 가슴에 직접 1·간접 0. 한 세트가 같은 근육에 직접+간접으로 겹치지 않는다.
- `GET /api/stats/advanced/attribution?from&to&include_warmup&indirect_weight=0.5` → 근육(level 2)별 `direct_sets`(= `/stats/muscles` level 2 `set_count`와 동일, 계약 테스트로 고정) · `indirect_sets`(가중 전) · `fractional_sets` · 볼륨 3종. 가중치는 조회 파라미터 — 저장하지 않는다(프론트 설정 persist).
- 마이그레이션 v4→v5: 테이블·VIEW 생성 + 보조 근육이 하나도 없는 내장 종목에 시드 초안을 **한 번만** 채움(`db._apply_v5_data`). 이후 관리자가 앱에서 비운 값을 재기동이 되살리지 않는다. 새로 추가되는 내장 종목은 `seed_exercises`가 INSERT 시점에 함께 넣는다. 데이터 파일을 고쳐도 이미 채워진 행에는 반영되지 않는다 — 그 행은 앱에서 수정.

### 11.3 고급 분석 6종 (`/api/stats/advanced/*`, 전부 read-only SQL 온디맨드)

| # | 엔드포인트 | 정의 | §6.2 |
|---|---|---|---|
| 1 | `frequency?weeks=8` | 근육·부위별 주별 **자극 세션 수**(웜업 제외) + 마지막 자극 경과일 + 방치(자극한 적 있고 `NEGLECT_DAYS`=14일 이상). 평균은 진행 중인 이번 주 제외. 한 번도 안 한 부위는 방치가 아니라 해당 없음 | B v2 |
| 2 | `trend?weeks=16` | 주간 볼륨 + `ma4`(이번 주 포함 4주 평균) + `acwr`(이번 주 ÷ 직전 4주 평균, `ACWR_WARN`=1.5 초과 경고). 쉰 주는 0으로 평균에 포함, 첫 훈련 주 이전 구간이 걸리면 null. 진행 중인 주는 `in_progress` — 경고 판정은 완료 주만 | A v2 |
| 3 | `rep-max?exercise_id` | 1~12RM 매트릭스: 정확히 그 횟수의 최고 중량 + 그 횟수 이상의 최고 중량(implied, 단조 감소). **Rep PR** = 같은 중량으로 이전 세션보다 많은 횟수 — §6.3 규칙 그대로(그 중량의 첫 세션은 베이스라인, strictly greater, 세션당 1건). 웜업·weight 0 제외 | C·D v2 |
| 4 | `fatigue?exercise_id&from&to` | 세션 안에서 그 종목의 n번째 워킹 세트 평균 횟수·중량·1세트 대비 비율(서수는 세션×종목 안에서 다시 매김, ≤10). 종목 rep range 분포(1-5 / 6-12 / 13-20 / 21+) | C v2 |
| 5 | `intensity?exercise_id?&from&to` | 세트 강도 = 중량 ÷ **그 시점까지** 그 종목의 최고 e1RM(러닝 최고치 — 과거를 현재 실력으로 재평가하지 않음, 100% 초과 없음). 존 <60/60-70/70-80/80-90/90+ 분포 + 평균 강도. 기간 필터는 집계에만, 러닝 최고치는 전체 이력. 맨몸·e1RM 없는 종목 세트 제외. 워킹 세트 전체 rep range 분포 | C v2 |
| 6 | `attribution` | §11.2 | B v2 |

### 11.4 UI

- 대시보드 하단 "고급 분석" 섹션(`components/dashboard/AdvancedAnalytics.tsx`): 잠금 카드(진행 바 n/4주, 열리는 항목 안내) 또는 카드 6종. 종목별 카드(rep-max·피로 곡선)는 '종목별 진행'의 선택 종목을 따른다.
- 종목 폼: "보조 근육" 칩 목록 + 추가(타겟 시트 재사용). 설정: "간접 세트 가중치" ⅓/½ (persist `indirectWeight`).
- 라인차트는 `components/charts/TrendLineChart.tsx`로 분리(대시보드·추세 카드 공용, 점선 시리즈 지원).

### 11.5 검증

- pytest 163 (신규 23: 게이트 5·분석 6종 값·계약 키·간접 규칙 (a)(b)(c)·총볼륨 불변·종목 API·마이그레이션 v3→v5/v4→v5·시드 정합성). tsc·vite build. 헤드리스 Edge 플로우: 0주 잠금 → 4주 시드 → 카드 6종 → 종목 폼 칩 → 설정 가중치 → 두 번째 사용자 잠금.

### 11.6 알고 수용하는 것 · 미결

1. 보조 근육 초안은 관례 기준이라 이견이 있는 항목이 있다 (스쿼트에 내전근 미포함, 풀오버의 가슴 0.5, 런지 비대칭 처리, 역도 계열 3개 상한 등). 데이터 파일 검토가 필요하며, 이미 마이그레이션된 DB는 앱에서 고쳐야 한다.
2. 간접 **볼륨(kg)** 은 세트 수만큼 표준적이지 않다(문헌은 세트 기준). 카드 기본은 세트, 볼륨은 토글.
3. 게이트 4주는 통계적 근거라기보다 이동평균 성립 조건. ACWR은 완료 주 4개가 더 필요해 실질적으로 5주째부터 값이 나온다.
4. 러닝 e1RM 기준 강도는 초기 데이터에서 과대(첫 세트가 곧 100%)될 수 있다. 데이터가 쌓이면 안정.
5. RP 랜드마크(MV/MEV/MAV/MRV)와 RPE 입력은 여전히 미구현 — `workout_set.rpe` 컬럼은 있으나 UI 없음.
6. CSV 내보내기에 보조 근육 컬럼은 넣지 않았다(계약 유지). 필요하면 별도 결정.

---

## 12. 외부 공개 방식 개정 (2026-09-10) — Cloudflare Tunnel, 이후 직접 노출

사용자 결정(2026-09-10 문답): "일단 B(Cloudflare Tunnel)로 하고, 나중에 NAS를 구축하면 A(직접 노출)로 바꾼다." 배경: 현재 Tailscale은 `serve`(tailnet only)라 지인이 쓰려면 Tailscale 앱 설치·초대가 필요하다. Funnel만 켜도 링크 접속은 되지만, 사용자는 내 도메인과 Tailscale 의존 제거를 원했다. §7.1의 Funnel 계획은 이 절이 대체한다.

### 12.1 세 가지 설계와 선택

| | A 직접 노출 | **B Cloudflare Tunnel (채택)** | C 클라우드 (§7.5) |
|---|---|---|---|
| 구조 | 브라우저 → DNS → 공유기 포트포워딩 443 → Caddy(TLS) → uvicorn 127.0.0.1:8000 | 브라우저 → Cloudflare 엣지(TLS) → 아웃바운드 터널(cloudflared 서비스) → uvicorn 127.0.0.1:8000 | 브라우저 → Fly.io → 컨테이너 + 볼륨 |
| 필요 | 공인 IP(CGNAT 불가), 포트포워딩, 도메인/DDNS, Caddy | 도메인 1개를 Cloudflare DNS에 등록, `cloudflared` 서비스 | Dockerfile·fly.toml, 백업 경로 변경 |
| 연구실 PC 가능 | 거의 불가(기관 인바운드 차단) | 가능(아웃바운드 443) | 해당 없음 |
| 앱 코드 수정 | 없음 | 없음 | 배포·백업 |
| 노출면 | 서버 직접 노출 | 엣지 뒤 | 엣지 뒤 |

B는 Tailscale Funnel과 원리가 같다(PC가 밖으로 연결, 인바운드 없음). 다른 점은 주소가 내 도메인이고 지인이 앱 설치 없이 링크로 접속한다는 것.

### 12.2 B 절차 (원격 관리 터널)

PC에 설정 파일을 두지 않고 대시보드에서 호스트명·라우팅을 관리한다. PC 쪽은 커넥터 서비스 하나.

1. 사용자: 도메인 구입 → Cloudflare에 사이트 추가(무료 플랜, 네임서버 변경).
2. 사용자: Zero Trust > Networks > Tunnels > Create > Cloudflared > 이름(예: `volume-app`) → Windows 커넥터 설치 명령에서 **토큰만** 복사 → Public Hostname: `volume.<도메인>` → Service HTTP `127.0.0.1:8000`.
3. 연구실 PC(관리자 PowerShell): `.\scripts\install-cloudflare-tunnel.ps1 -Token "<토큰>"` — winget으로 cloudflared 설치, Windows 서비스 등록(부팅 자동 시작), 상태 출력. `-Status`·`-Uninstall` 제공.
4. 확인: 대시보드 터널 상태 HEALTHY, 폰 LTE에서 `https://volume.<도메인>` 접속.

운영 규칙:
- cloudflared 서비스는 `VolumeApp-StartServer` 예약 작업과 독립이다. 앱이 죽어도 터널은 살아 있고(엣지가 502), 앱이 살아나면 자동 복구.
- 앱은 계속 `127.0.0.1`만 듣는다. Windows 방화벽 인바운드 개방·포트포워딩 없음.
- Tailscale: **2026-09-14 `tailscale funnel --bg 8000` 실행 → Funnel ON(공개)**. 사용자 지시로 켰고, 연구실망에서 Funnel이 막히지 않음을 확인했다(공개 DNS(DoH)로 Funnel 입구 IP 103.84.155.153/.217 확인, 그 IP로 강제 접속 시 `/health`·index 200, 8/8 성공). **같은 날 노드 이름을 `desktop-8k13b1r` → `volume`으로 변경**(`tailscale set --hostname volume`, `tailscale serve reset`, `tailscale funnel --bg 8000`) → 공개 주소 **`https://volume.tail6df393.ts.net`**. 이름 변경 후 새 인증서 발급까지 약 40초 TLS 실패 뒤 정상. 옛 주소는 죽었다(설정 없음). Cloudflare Tunnel로 옮기기 전까지 이 주소가 지인 공개 링크다. 끄기: `tailscale funnel --https=443 off`(tailnet 내부 `serve`는 남는다). 두 경로가 동시에 같은 서버를 가리켜도 무방. 주의: 이 PC에서 ts.net 주소를 열면 NRPT 규칙(100.100.100.100)이 가로채 tailnet 경로로 가므로 외부 검증은 DoH+`--resolve` 또는 폰 LTE로 한다.
- 캐시: 앱이 보내는 `Cache-Control`(HTML no-cache, /assets immutable, /api no-store)을 Cloudflare가 그대로 따른다. 배포 후 index.html은 매번 재검증되므로 별도 캐시 퍼지는 불필요.

### 12.3 공개에 따른 보안 메모

공개 URL이 되면 누구나 가입 화면에 닿는다(§10.1 보안 최소 정책은 유지). 최소 장치 두 가지 중 하나를 권장하며 **둘 다 미구현·미결정**:
- 앱: `.env` `INVITE_CODE`를 가입 시 요구(코드 20줄 규모).
- Cloudflare Access(무료): 이메일 OTP 관문을 앱 앞에 둔다. 코드 수정 없음, 지인 이메일을 허용 목록에 등록.

### 12.4 이후 A(직접 노출)로의 전환 — NAS 구축 시

- 서버(uvicorn + SQLite + 백업)는 NAS(또는 NAS 옆 PC)로 이전. 앱은 여전히 127.0.0.1:8000.
- 앞단: Caddy(또는 NAS 내장 리버스 프록시) `:443` → `127.0.0.1:8000`, Let's Encrypt 자동. 공유기 443 포트포워딩. DNS는 이미 Cloudflare에 있으니 A 레코드만 집 공인 IP로 바꾸면 되고, IP가 바뀌면 Cloudflare API로 갱신하는 DDNS 스크립트를 둔다.
- 전환 전 확인: 집 회선 공인 IP 여부(CGNAT이면 A 불가 → B 유지), 통신사 443 인바운드 허용 여부.
- 전환 시 B의 cloudflared 서비스는 `-Uninstall`로 제거. 대시보드 터널도 삭제.
- 직접 노출은 서버가 인터넷에 그대로 보이므로 그 시점에는 12.3의 장치 중 하나를 반드시 켠다.

### 12.5 알고 수용하는 것

1. 도메인 비용(연 1~2만 원)과 Cloudflare 계정 의존이 생긴다. 무료 플랜 정책 변경 시 Funnel(무료)로 되돌릴 수 있다 — 구조가 같다.
2. 지인 데이터가 공개 URL 아래 놓인다는 §10.1 고지는 그대로다.
3. 4주 게이트·랜드마크 등 앱 기능 결정과 무관한, 네트워크만의 변경이다.
