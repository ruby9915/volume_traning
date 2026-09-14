import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  apiErrorMessage,
  changePassword,
  downloadExport,
  fetchBodyweight,
  logout,
  saveBodyweight,
} from "../api/client";
import type { BodyWeightEntry } from "../api/types";
import Button from "../components/Button";
import Card from "../components/Card";
import Spinner from "../components/Spinner";
import MachinePicker from "../components/machine/MachinePicker";
import { useMe } from "../hooks/useMe";
import { useMyMachines } from "../hooks/useMyMachines";
import {
  INDIRECT_WEIGHT_OPTIONS,
  REST_TARGET_OPTIONS,
  TARGET_BACKFILL_OPTIONS,
  useAppStore,
  type IndirectWeight,
  type TargetBackfillMode,
  type WeightStep,
} from "../store";
import { THEME_OPTIONS, setThemePref, useThemePref, type ThemePref } from "../theme";
import { formatKoreanDate, todayStr } from "../utils/date";

const WEIGHT_STEPS: WeightStep[] = [1.25, 2.5, 5];
const HISTORY_LIMIT = 30;

const THEME_LABELS: Record<ThemePref, string> = {
  system: "시스템",
  light: "라이트",
  dark: "다크",
};

function errorText(e: unknown): string {
  return apiErrorMessage(e, "네트워크 오류 — 연결을 확인하세요");
}

function SectionTitle({ children }: { children: string }) {
  return <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted">{children}</h2>;
}

/** 설정 선택지 공용 버튼 (세그먼트형) */
function ChoiceButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`touch-target rounded-btn border text-sm font-semibold tabular-nums transition-colors ${
        active
          ? "border-accent bg-accent/15 text-accent"
          : "border-line bg-surface-2 text-muted active:bg-line"
      }`}
    >
      {children}
    </button>
  );
}

const FIELD_CLS =
  "touch-target w-full rounded-row border border-line bg-well px-4 text-base placeholder:text-faint focus:border-accent focus:outline-none";

function ThemeSection() {
  const themePref = useThemePref();
  return (
    <Card>
      <SectionTitle>테마</SectionTitle>
      <div className="grid grid-cols-3 gap-2">
        {THEME_OPTIONS.map((pref) => (
          <ChoiceButton key={pref} active={themePref === pref} onClick={() => setThemePref(pref)}>
            {THEME_LABELS[pref]}
          </ChoiceButton>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        시스템: 기기 다크모드 설정을 따릅니다. 다크 IRON / 라이트 FRESH.
      </p>
    </Card>
  );
}

function RestTargetSection() {
  const restTarget = useAppStore((s) => s.restTargetSeconds);
  const setRestTarget = useAppStore((s) => s.setRestTarget);
  return (
    <Card>
      <SectionTitle>휴식 목표시간</SectionTitle>
      <div className="grid grid-cols-5 gap-2">
        {REST_TARGET_OPTIONS.map((sec) => (
          <ChoiceButton key={sec} active={restTarget === sec} onClick={() => setRestTarget(sec)}>
            {sec >= 120 ? `${sec / 60}분` : `${sec}초`}
          </ChoiceButton>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">기록 화면 휴식 타이머 진행바의 목표시간입니다.</p>
    </Card>
  );
}

function WeightStepSection() {
  const weightStep = useAppStore((s) => s.weightStep);
  const setWeightStep = useAppStore((s) => s.setWeightStep);

  return (
    <Card>
      <SectionTitle>중량 스테퍼 증분</SectionTitle>
      <div className="grid grid-cols-3 gap-2">
        {WEIGHT_STEPS.map((step) => (
          <ChoiceButton key={step} active={weightStep === step} onClick={() => setWeightStep(step)}>
            {`${step} kg`}
          </ChoiceButton>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">기록 화면 중량 ± 버튼의 증분입니다.</p>
    </Card>
  );
}

const TARGET_BACKFILL_LABELS: Record<TargetBackfillMode, string> = {
  ask: "물어보기",
  always: "항상 적용",
  never: "적용 안 함",
};

// §10.2 소급 적용 확인의 설정화 — 확인 다이얼로그의 "다시 묻지 않기"와 같은 값을 공유
function TargetBackfillSection() {
  const mode = useAppStore((s) => s.targetBackfill);
  const setMode = useAppStore((s) => s.setTargetBackfill);
  return (
    <Card>
      <SectionTitle>타겟 변경 시 기존 세트</SectionTitle>
      <div className="grid grid-cols-3 gap-2">
        {TARGET_BACKFILL_OPTIONS.map((m) => (
          <ChoiceButton key={m} active={mode === m} onClick={() => setMode(m)}>
            {TARGET_BACKFILL_LABELS[m]}
          </ChoiceButton>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        기록 화면에서 종목 카드의 타겟 부위를 바꿀 때, 이미 저장된 같은 종목 세트에도 적용할지 처리
        방식입니다.
      </p>
    </Card>
  );
}

const INDIRECT_WEIGHT_LABELS: Record<IndirectWeight, string> = {
  0.33: "⅓ (0.33)",
  0.5: "½ (0.5)",
};

// §11.2 간접 세트 가중치 — 고급 분석 '관여 근육 분배'에서만 쓰인다 (총볼륨·PR 무관)
function IndirectWeightSection() {
  const weight = useAppStore((s) => s.indirectWeight);
  const setWeight = useAppStore((s) => s.setIndirectWeight);
  return (
    <Card>
      <SectionTitle>간접 세트 가중치</SectionTitle>
      <div className="grid grid-cols-2 gap-2">
        {INDIRECT_WEIGHT_OPTIONS.map((w) => (
          <ChoiceButton key={w} active={weight === w} onClick={() => setWeight(w)}>
            {INDIRECT_WEIGHT_LABELS[w]}
          </ChoiceButton>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        고급 분석의 &lsquo;관여 근육 분배&rsquo;에서 보조 근육이 받는 세트 가중치입니다. 메인 볼륨·PR은
        항상 타겟 부위 100%로 계산되며 이 값의 영향을 받지 않습니다.
      </p>
    </Card>
  );
}

// §10.4 내 머신 — 종목 폼의 머신 칸에 보이는 목록. 아카이브(1,400+대) 검색으로 담고 여기서 뺀다.
function MyMachinesSection() {
  const mine = useMyMachines();
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <SectionTitle>내 머신</SectionTitle>
      {mine.isLoading ? (
        <div className="flex justify-center py-4">
          <Spinner size="sm" />
        </div>
      ) : mine.machines.length === 0 ? (
        <p className="mb-3 text-sm text-muted">
          아직 담은 머신이 없습니다. 헬스장에 있는 머신을 검색해 담아 두면 종목 폼에서 바로 고를 수 있습니다.
        </p>
      ) : (
        <ul className="mb-3 divide-y divide-line border-t border-line">
          {mine.machines.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="min-w-0">
                <span className="block truncate font-semibold">{m.name_ko}</span>
                <span className="block truncate text-xs text-muted">
                  {m.brand} · {m.model}
                </span>
              </span>
              <button
                type="button"
                onClick={() => mine.remove(m.id)}
                disabled={mine.isMutating}
                className="touch-target shrink-0 text-sm text-muted underline underline-offset-2 active:text-text"
              >
                빼기
              </button>
            </li>
          ))}
        </ul>
      )}
      <Button variant="secondary" full onClick={() => setOpen(true)}>
        ＋ 아카이브에서 검색해 담기
      </Button>
      <p className="mt-2 text-xs text-muted">
        종목의 머신 칸에는 이 목록만 보입니다. 아카이브 전체는 검색으로만 엽니다.
      </p>
      <MachinePicker
        open={open}
        onClose={() => setOpen(false)}
        onPick={(m) => {
          setOpen(false);
          void mine.add(m.id).catch(() => undefined);
        }}
      />
    </Card>
  );
}

function BodyweightSection() {
  const [entries, setEntries] = useState<BodyWeightEntry[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const data = await fetchBodyweight(HISTORY_LIMIT);
      setEntries([...data].sort((a, b) => b.date.localeCompare(a.date)));
    } catch (e) {
      setEntries([]);
      setLoadError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const latest = entries?.[0] ?? null;

  const save = async () => {
    const v = Math.round(parseFloat(input) * 100) / 100;
    if (!Number.isFinite(v) || v <= 0 || v > 500) {
      setSaveError("체중은 0보다 크고 500 이하인 숫자로 입력하세요");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await saveBodyweight({ date: todayStr(), weight_kg: v });
      setInput("");
      await load();
    } catch (e) {
      setSaveError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <SectionTitle>현재 체중</SectionTitle>
      {entries === null ? (
        <div className="flex justify-center py-4">
          <Spinner size="sm" />
        </div>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted">
            {latest ? (
              <>
                최근 기록:{" "}
                <span className="font-numeric font-semibold text-text">{latest.weight_kg} kg</span>{" "}
                ({formatKoreanDate(latest.date)})
              </>
            ) : (
              "기록 없음 — 맨몸 운동 볼륨 계산에 사용됩니다."
            )}
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              inputMode="decimal"
              placeholder={latest ? String(latest.weight_kg) : "예: 72.5"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void save();
              }}
              className={`${FIELD_CLS} min-w-0 flex-1 font-numeric`}
            />
            <Button onClick={() => void save()} disabled={saving || input.trim() === ""}>
              {saving ? <Spinner size="sm" /> : "저장"}
            </Button>
          </div>
          {saveError ? <p className="mt-2 text-sm text-danger">{saveError}</p> : null}
          {loadError ? <p className="mt-2 text-sm text-danger">{loadError}</p> : null}
          {entries.length > 0 ? (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setShowHistory((v) => !v)}
                className="text-sm text-muted underline underline-offset-2 active:text-text"
              >
                {showHistory ? "이력 접기" : `이력 보기 (${entries.length})`}
              </button>
              {showHistory ? (
                <ul className="mt-2 divide-y divide-line border-t border-line">
                  {entries.map((e) => (
                    <li key={e.id} className="flex justify-between py-2 text-sm">
                      <span className="text-muted">{e.date}</span>
                      <span className="font-numeric">{e.weight_kg} kg</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function ExportSection({ isAdmin }: { isAdmin: boolean }) {
  const [busy, setBusy] = useState<"db" | "csv" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (kind: "db" | "csv") => {
    setBusy(kind);
    setError(null);
    try {
      await downloadExport(kind);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <SectionTitle>데이터 내보내기</SectionTitle>
      <div className={`grid gap-2 ${isAdmin ? "grid-cols-2" : "grid-cols-1"}`}>
        <Button variant="secondary" disabled={busy !== null} onClick={() => void run("csv")}>
          {busy === "csv" ? <Spinner size="sm" className="mx-auto" /> : "CSV 다운로드"}
        </Button>
        {isAdmin ? (
          <Button variant="secondary" disabled={busy !== null} onClick={() => void run("db")}>
            {busy === "db" ? <Spinner size="sm" className="mx-auto" /> : "DB 백업 다운로드"}
          </Button>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-muted">
        CSV는 내 세트 기록 전체(Excel 호환)입니다.
        {isAdmin ? " DB는 전체 사용자 데이터가 담긴 SQLite 스냅샷이라 관리자만 받을 수 있습니다." : ""}
      </p>
      {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
    </Card>
  );
}

// §10.1 비밀번호 변경 — 사용자 테이블이 생기면서 앱에서 바꿀 수 있게 됐다
function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 4) {
      setMsg({ ok: false, text: "새 비밀번호는 4자 이상이어야 합니다." });
      return;
    }
    if (next !== confirm) {
      setMsg({ ok: false, text: "새 비밀번호 확인이 일치하지 않습니다." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await changePassword({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      setMsg({ ok: true, text: "비밀번호를 변경했습니다." });
    } catch (err) {
      setMsg({
        ok: false,
        text:
          err instanceof ApiError && err.status === 401
            ? "현재 비밀번호가 올바르지 않습니다."
            : errorText(err),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="mt-3 flex flex-col gap-2">
      <input
        type="password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        placeholder="현재 비밀번호"
        autoComplete="current-password"
        className={FIELD_CLS}
      />
      <input
        type="password"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        placeholder="새 비밀번호 (4자 이상)"
        autoComplete="new-password"
        className={FIELD_CLS}
      />
      <input
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder="새 비밀번호 확인"
        autoComplete="new-password"
        className={FIELD_CLS}
      />
      {msg ? <p className={`text-sm ${msg.ok ? "text-accent" : "text-danger"}`}>{msg.text}</p> : null}
      <Button type="submit" variant="secondary" disabled={busy || !current || !next}>
        {busy ? "변경 중…" : "비밀번호 변경"}
      </Button>
    </form>
  );
}

export default function Settings() {
  const navigate = useNavigate();
  const me = useMe();

  return (
    <main className="mx-auto max-w-[720px] p-4 safe-bottom">
      <header className="mb-4 flex items-center gap-1">
        <button
          type="button"
          aria-label="뒤로"
          onClick={() => navigate(-1)}
          className="touch-target -ml-3 rounded-xl text-2xl text-muted active:bg-surface-2"
        >
          ‹
        </button>
        <h1 className="text-xl font-bold">설정</h1>
      </header>

      <div className="flex flex-col gap-3">
        <ThemeSection />
        <WeightStepSection />
        <RestTargetSection />
        <TargetBackfillSection />
        <IndirectWeightSection />
        <MyMachinesSection />
        <BodyweightSection />
        <ExportSection isAdmin={me.data?.is_admin ?? false} />
        <Card>
          <SectionTitle>계정</SectionTitle>
          <p className="text-sm">
            <span className="font-semibold">{me.data?.display_name ?? "…"}</span>
            {me.data ? <span className="ml-2 text-muted">@{me.data.username}</span> : null}
            {me.data?.is_admin ? (
              <span className="ml-2 rounded-tag bg-accent-glow px-1.5 py-0.5 text-[10px] font-bold text-accent">
                관리자
              </span>
            ) : null}
          </p>
          <PasswordSection />
          <Button variant="danger" full className="mt-4" onClick={() => logout()}>
            로그아웃
          </Button>
        </Card>
      </div>
    </main>
  );
}
