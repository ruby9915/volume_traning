import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchSessions } from "../api/client";
import type { SessionSummary } from "../api/types";
import Button from "../components/Button";
import Card from "../components/Card";
import ErrorRetry from "../components/ErrorRetry";
import Spinner from "../components/Spinner";
import { formatFullDate, todayStr } from "../utils/date";
import { fmtInt } from "../utils/format";

const CAL_HEADERS = ["월", "화", "수", "목", "금", "토", "일"];
const PAGE_SIZE = 20;

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// 일별 볼륨 단색 농도 (잔디 스타일) — 해당 월 최대 볼륨 대비 4단계, accent 계열
function intensityClass(volume: number, max: number): string {
  if (volume <= 0 || max <= 0) return "";
  const r = volume / max;
  if (r > 0.75) return "bg-accent font-semibold text-on-accent";
  if (r > 0.5) return "bg-accent/55";
  if (r > 0.25) return "bg-accent/30";
  return "bg-accent/15";
}

interface DayAgg {
  volume: number;
  sessions: SessionSummary[];
}

function DateHeader({ date }: { date: string }) {
  return (
    <h2 className="mb-2 font-numeric text-xs font-semibold tracking-wide text-muted">
      {formatFullDate(date)}
    </h2>
  );
}

// 세션 카드 — 기록 화면 완료 종목 카드 패턴 (Card sunken): 총볼륨 숫자폰트 강조 + 요약 줄 + 부위 라벨
// 부위 라벨(§10.2)은 분할표 없이 그날 세트의 타겟에서 도출된다 ("하체·등" 형태)
export function SessionCard({
  session,
  onClick,
}: {
  session: SessionSummary;
  onClick?: () => void;
}) {
  const navigate = useNavigate();
  return (
    <Card variant="sunken" className="mb-2" onClick={onClick ?? (() => navigate(`/history/${session.id}`))}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-numeric text-2xl font-bold leading-tight dark:font-semibold">
          {fmtInt(session.total_volume)}
          <span className="ml-1 text-sm font-normal text-muted dark:uppercase">kg</span>
        </p>
        <span className="flex shrink-0 items-center gap-1.5">
          {session.region_label && (
            <span className="rounded-tag bg-accent-glow px-2 py-0.5 text-[11px] font-bold text-accent">
              {session.region_label}
            </span>
          )}
          <span className="text-muted">›</span>
        </span>
      </div>
      <p className="mt-1 font-numeric text-sm text-muted">
        {session.exercise_count}종목 · {session.set_count}세트
        {session.note ? ` · ${session.note}` : ""}
      </p>
    </Card>
  );
}

function CalendarView() {
  const navigate = useNavigate();
  const today = todayStr();
  const thisMonth = today.slice(0, 7);
  const [month, setMonth] = useState(thisMonth);
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState<string | null>(today);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setSessions(null);
    setError(false);
    const [y, m] = month.split("-").map(Number);
    const lastDay = new Date(y, m, 0).getDate();
    fetchSessions({
      from: `${month}-01`,
      to: `${month}-${String(lastDay).padStart(2, "0")}`,
      limit: 200,
    })
      .then((rows) => {
        if (alive) setSessions(rows);
      })
      .catch(() => {
        if (alive) setError(true);
      });
    return () => {
      alive = false;
    };
  }, [month, reloadKey]);

  const byDate = new Map<string, DayAgg>();
  for (const s of sessions ?? []) {
    const agg = byDate.get(s.date) ?? { volume: 0, sessions: [] };
    agg.volume += s.total_volume;
    agg.sessions.push(s);
    byDate.set(s.date, agg);
  }
  const maxVolume = Math.max(0, ...[...byDate.values()].map((a) => a.volume));

  const [year, monthNum] = month.split("-").map(Number);
  const daysInMonth = new Date(year, monthNum, 0).getDate();
  const leading = (new Date(year, monthNum - 1, 1).getDay() + 6) % 7; // 월요일 시작
  const cells: (number | null)[] = [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const moveMonth = (delta: number) => {
    const next = shiftMonth(month, delta);
    setMonth(next);
    setSelected(next === thisMonth ? today : null);
  };

  const selectedAgg = selected ? byDate.get(selected) : undefined;

  return (
    <div>
      <div className="mt-4 flex items-center justify-between">
        <button
          type="button"
          aria-label="이전 달"
          className="touch-target rounded-row text-xl text-muted active:bg-surface-2"
          onClick={() => moveMonth(-1)}
        >
          ‹
        </button>
        <span className="font-numeric font-bold">
          {year}년 {monthNum}월
        </span>
        <button
          type="button"
          aria-label="다음 달"
          className="touch-target rounded-row text-xl text-muted active:bg-surface-2"
          onClick={() => moveMonth(1)}
        >
          ›
        </button>
      </div>

      {error ? (
        <ErrorRetry className="py-10" onRetry={() => setReloadKey((k) => k + 1)} />
      ) : sessions === null ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : (
        <>
          <div className="mt-2 grid grid-cols-7 gap-1 text-center">
            {CAL_HEADERS.map((h) => (
              <span key={h} className="py-1 text-xs text-muted">
                {h}
              </span>
            ))}
            {cells.map((day, i) => {
              if (day === null) return <span key={`blank-${i}`} />;
              const dateStr = `${month}-${String(day).padStart(2, "0")}`;
              const agg = byDate.get(dateStr);
              const isSelected = selected === dateStr;
              const isToday = dateStr === today;
              return (
                <button
                  key={dateStr}
                  type="button"
                  onClick={() => setSelected(dateStr)}
                  className={`aspect-square rounded-row font-numeric text-sm ${intensityClass(agg?.volume ?? 0, maxVolume)} ${
                    isSelected ? "ring-2 ring-accent" : ""
                  } ${isToday && !agg ? "font-semibold text-accent" : ""}`}
                >
                  {day}
                </button>
              );
            })}
          </div>

          <section className="mt-5">
            {selected === null ? (
              <p className="text-sm text-muted">날짜를 선택하면 세션 요약이 표시됩니다.</p>
            ) : (
              <>
                <DateHeader date={selected} />
                {!selectedAgg ? (
                  <>
                    <p className="text-sm text-muted">기록이 없습니다.</p>
                    {/* §3.7B 빈 날짜에 과거 기록 생성 — 미래 날짜는 제외 */}
                    {selected <= today && (
                      <Button
                        variant="secondary"
                        className="mt-3"
                        onClick={() => navigate(`/history/new?date=${selected}`)}
                      >
                        ＋ 이 날짜에 기록 추가
                      </Button>
                    )}
                  </>
                ) : (
                  selectedAgg.sessions.map((s) => <SessionCard key={s.id} session={s} />)
                )}
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function ListView() {
  const [items, setItems] = useState<SessionSummary[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const offsetRef = useRef(0);
  const loadingRef = useRef(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const loadMore = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    setError(false);
    try {
      const rows = await fetchSessions({ limit: PAGE_SIZE, offset: offsetRef.current });
      offsetRef.current += rows.length;
      setItems((prev) => [...prev, ...rows]);
      if (rows.length < PAGE_SIZE) setHasMore(false);
    } catch {
      setError(true);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!hasMore || error) return;
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) void loadMore();
      },
      { rootMargin: "300px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasMore, error, loadMore, items.length]);

  // 날짜 헤더 + 세션 카드 — 서버가 날짜 내림차순으로 주므로 연속 구간만 묶으면 된다
  const sections = useMemo(() => {
    const out: { date: string; sessions: SessionSummary[] }[] = [];
    for (const s of items) {
      const last = out[out.length - 1];
      if (last && last.date === s.date) last.sessions.push(s);
      else out.push({ date: s.date, sessions: [s] });
    }
    return out;
  }, [items]);

  return (
    <div className="mt-4">
      {sections.map((sec) => (
        <section key={sec.date} className="mb-4">
          <DateHeader date={sec.date} />
          {sec.sessions.map((s) => (
            <SessionCard key={s.id} session={s} />
          ))}
        </section>
      ))}
      {!hasMore && items.length === 0 && (
        <p className="py-10 text-center text-sm text-muted">아직 기록된 세션이 없습니다.</p>
      )}
      {error && <ErrorRetry className="py-10" onRetry={() => void loadMore()} />}
      {loading && (
        <div className="flex justify-center py-4">
          <Spinner size="sm" />
        </div>
      )}
      {hasMore && !error && <div ref={sentinelRef} className="h-1" />}
    </div>
  );
}

export default function History() {
  const [view, setView] = useState<"calendar" | "list">("calendar");

  // 분석 화면 세그먼트 토글 패턴: 라이트 = 잉크 필 + 흰 텍스트 / 다크 = bg색 세그먼트
  const toggleCls = (active: boolean) =>
    `touch-target rounded-field text-sm transition-colors ${
      active ? "bg-text font-bold text-surface dark:bg-bg dark:text-text" : "font-medium text-muted"
    }`;

  return (
    <main className="mx-auto max-w-[720px] p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-[19px] font-extrabold dark:font-numeric dark:text-[13px] dark:font-semibold dark:tracking-[3px] dark:uppercase dark:text-muted">
          <span className="dark:hidden">이력</span>
          <span className="hidden dark:inline">History</span>
        </h1>
        <Link
          to="/settings"
          aria-label="설정"
          className="touch-target flex items-center justify-center rounded-row text-xl text-muted active:bg-surface-2"
        >
          ⚙
        </Link>
      </header>

      <div className="mt-3 grid grid-cols-2 gap-1 rounded-field bg-surface p-1 shadow-card">
        <button type="button" className={toggleCls(view === "calendar")} onClick={() => setView("calendar")}>
          캘린더
        </button>
        <button type="button" className={toggleCls(view === "list")} onClick={() => setView("list")}>
          리스트
        </button>
      </div>

      {view === "calendar" ? <CalendarView /> : <ListView />}
    </main>
  );
}
