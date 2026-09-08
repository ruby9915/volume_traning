import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiErrorMessage, downloadExport, fetchBodyweight, logout, saveBodyweight } from "../api/client";
import type { BodyWeightEntry } from "../api/types";
import Button from "../components/Button";
import Card from "../components/Card";
import Spinner from "../components/Spinner";
import {
  INTENT_BACKFILL_OPTIONS,
  REST_TARGET_OPTIONS,
  useAppStore,
  type IntentBackfillMode,
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

const INTENT_BACKFILL_LABELS: Record<IntentBackfillMode, string> = {
  ask: "물어보기",
  always: "항상 적용",
  never: "적용 안 함",
};

// §3.7A 소급 적용 확인의 설정화 — 확인 다이얼로그의 "다시 묻지 않기"와 같은 값을 공유
function IntentBackfillSection() {
  const mode = useAppStore((s) => s.intentBackfill);
  const setMode = useAppStore((s) => s.setIntentBackfill);
  return (
    <Card>
      <SectionTitle>의도 변경 시 기존 세트</SectionTitle>
      <div className="grid grid-cols-3 gap-2">
        {INTENT_BACKFILL_OPTIONS.map((m) => (
          <ChoiceButton key={m} active={mode === m} onClick={() => setMode(m)}>
            {INTENT_BACKFILL_LABELS[m]}
          </ChoiceButton>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        기록 화면에서 의도 주동근을 바꿀 때, 이미 저장된 같은 종목 세트에도 적용할지 처리
        방식입니다.
      </p>
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
                <span className="font-numeric font-semibold text-text">
                  {latest.weight_kg} kg
                </span>{" "}
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
              className="touch-target min-w-0 flex-1 rounded-row border border-line bg-well px-4 font-numeric text-base placeholder:text-faint focus:border-accent focus:outline-none"
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

function ExportSection() {
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
      <div className="grid grid-cols-2 gap-2">
        <Button variant="secondary" disabled={busy !== null} onClick={() => void run("csv")}>
          {busy === "csv" ? <Spinner size="sm" className="mx-auto" /> : "CSV 다운로드"}
        </Button>
        <Button variant="secondary" disabled={busy !== null} onClick={() => void run("db")}>
          {busy === "db" ? <Spinner size="sm" className="mx-auto" /> : "DB 백업 다운로드"}
        </Button>
      </div>
      <p className="mt-2 text-xs text-muted">
        CSV는 전체 세트 기록(Excel 호환), DB는 SQLite 스냅샷입니다.
      </p>
      {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
    </Card>
  );
}

export default function Settings() {
  const navigate = useNavigate();

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
        <IntentBackfillSection />
        <BodyweightSection />
        <ExportSection />
        <Card>
          <SectionTitle>계정</SectionTitle>
          <Button variant="danger" full onClick={() => logout()}>
            로그아웃
          </Button>
          <p className="mt-2 text-xs text-muted">
            비밀번호 변경은 서버의 backend/.env 수정 후 재시작으로만 가능합니다.
          </p>
        </Card>
      </div>
    </main>
  );
}
