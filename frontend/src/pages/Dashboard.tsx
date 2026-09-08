import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchExercises,
  fetchFamily,
  fetchStatsExercise,
  fetchStatsMuscles,
  fetchStatsPrs,
  fetchStatsSummary,
  fetchStatsVolume,
} from "../api/client";
import { REGION_NAMES_KO } from "../api/types";
import type { Region, VolumePoint } from "../api/types";
import { addDays, formatKoreanDate, formatShortDate, todayStr, weekStartStr } from "../utils/date";
import { fmtInt, fmtK, fmtKg1 } from "../utils/format";
import { useResolvedTheme } from "../theme";
import Card from "../components/Card";
import ErrorRetry from "../components/ErrorRetry";
import Spinner from "../components/Spinner";

type PeriodMode = "weekly" | "monthly";

/**
 * 종목 진행 드롭다운 선택 — §3.6: 계열(base_movement) 항목 추가.
 * 계열은 exercise_id가 아니므로 판별 유니온으로 분리 (속성=분류, 정체성=행).
 */
type ProgressSelection =
  | { kind: "exercise"; id: number }
  | { kind: "family"; base: string };

/** select option value 직렬화 — 종목은 숫자 id, 계열은 "family:" 접두 (충돌 없음) */
const FAMILY_PREFIX = "family:";

const REGION_ORDER = Object.keys(REGION_NAMES_KO) as Region[];

/**
 * 부위별 분배 램프 — 시안은 5단계(--color-ramp-1..5), 우리 region은 6개라
 * 마지막 단계를 같은 톤 방향으로 1단계 연장(코어 포함 6행).
 * 1..5는 CSS 변수를 그대로 참조하고, 6번째만 테마 분기.
 */
const RAMP_VARS = [1, 2, 3, 4, 5].map((n) => `var(--color-ramp-${n})`);
const RAMP_6 = { light: "#d3efe2", dark: "#443027" } as const;

/**
 * recharts는 색을 SVG presentation attribute로 내보내는데, attribute에서는
 * var()가 해석되지 않아 토큰 값을 hex로 미러링한다 (index.css @theme와 동기).
 */
const LINE_CHART_THEME = {
  light: { grid: "#e3e7e1", tick: "#71806f", top: "#0fa96f", e1rm: "#9aa89a", dotStroke: "#ffffff" },
  dark: { grid: "#2a2620", tick: "#8a8378", top: "#ff4a1f", e1rm: "#8a8378", dotStroke: "#171512" },
} as const;

const tooltipStyles = {
  contentStyle: {
    backgroundColor: "var(--color-surface)",
    border: "1px solid var(--color-line)",
    borderRadius: 10,
    fontSize: 12,
    padding: "6px 10px",
    boxShadow: "var(--shadow-card)",
  },
  labelStyle: { color: "var(--color-muted)", marginBottom: 2 },
  itemStyle: { color: "var(--color-text)", padding: "1px 0" },
};

function buildPeriods(mode: PeriodMode, today: string): string[] {
  if (mode === "weekly") {
    const start = addDays(weekStartStr(today), -7 * 11);
    return Array.from({ length: 12 }, (_, i) => addDays(start, i * 7));
  }
  const [y, m] = today.split("-").map(Number);
  const base = y * 12 + (m - 1);
  return Array.from({ length: 12 }, (_, i) => {
    const t = base - 11 + i;
    return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`;
  });
}

function periodLabel(mode: PeriodMode, period: string): string {
  if (mode === "weekly") return formatShortDate(period);
  return `${period.slice(2, 4)}.${Number(period.slice(5, 7))}`;
}

function CardTitle({ title, note }: { title: string; note?: string }) {
  return (
    <div className="mb-4 flex items-baseline gap-1.5">
      <h2 className="text-[15px] font-bold">{title}</h2>
      {note && <span className="text-[11px] text-muted">· {note}</span>}
    </div>
  );
}

function Loading() {
  return (
    <div className="flex justify-center py-8">
      <Spinner />
    </div>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="py-6 text-center text-sm text-muted">{text}</p>;
}

/** 히어로 12구간 바 차트 — 과거 3단계 톤 + 현재 구간만 accent(+상시 값 라벨) */
function HeroBarChart({
  rows,
  selected,
  onSelect,
}: {
  rows: { label: string; volume: number }[];
  selected: number | null;
  onSelect: (i: number | null) => void;
}) {
  const n = rows.length;
  const maxVol = Math.max(...rows.map((r) => r.volume), 1);
  return (
    <div className="mt-5">
      <div className="flex h-[140px] items-end gap-1">
        {rows.map((r, i) => {
          const isNow = i === n - 1;
          // 값 라벨 headroom 확보를 위해 최대 86%까지만 사용
          const pct = Math.max((r.volume / maxVol) * 86, 2);
          const showLabel = isNow || i === selected;
          const histStage = i < 4 ? 1 : i < 8 ? 2 : 3;
          return (
            <button
              key={i}
              type="button"
              onClick={() => onSelect(isNow || selected === i ? null : i)}
              className="relative flex h-full flex-1 items-end"
              aria-label={`${r.label} ${fmtInt(r.volume)}kg`}
            >
              {showLabel && (
                <span
                  className="absolute left-1/2 -translate-x-1/2 font-numeric text-[11px] font-bold whitespace-nowrap text-hero-accent"
                  style={{ bottom: `calc(${pct}% + 4px)` }}
                >
                  {fmtK(r.volume)}
                </span>
              )}
              <span
                className="block w-full rounded-[3px]"
                style={{
                  height: `${pct}%`,
                  transition: "height .3s ease",
                  background: isNow
                    ? "linear-gradient(180deg, var(--color-bar-now-from), var(--color-bar-now-to))"
                    : `var(--color-bar-hist-${histStage})`,
                }}
              />
            </button>
          );
        })}
      </div>
      {/* x축 라벨: 다크=faint(README L63), 라이트 잉크카드는 hero-muted가 대응 토큰 */}
      <div className="mt-2 flex justify-between text-[9px] text-hero-muted dark:text-faint">
        <span>{rows[0]?.label}</span>
        <span>{rows[Math.floor(n / 2)]?.label}</span>
        <span>{rows[n - 1]?.label}</span>
      </div>
    </div>
  );
}

interface TrendSeries {
  key: string;
  name: string;
  color: string;
  /** 이중 축(dualAxis)일 때 우축에 붙일 시리즈 */
  rightAxis?: boolean;
  /** null 구간을 이어 그린다 (e1RM은 reps>12 세션에서 null) */
  connectNulls?: boolean;
  /** 툴팁 값 포맷 — 기본 소수 1자리 */
  format?: (v: number) => string;
}

/**
 * 종목별·계열 진행 라인차트 — 두 카드가 같은 스타일(그리드·축·점·범례)을 공유한다.
 * dualAxis: 좌축(볼륨)과 우축(e1RM)처럼 스케일이 다른 시리즈를 한 차트에 그릴 때.
 */
function TrendLineChart({
  data,
  series,
  dualAxis = false,
}: {
  data: Record<string, string | number | null>[];
  series: TrendSeries[];
  dualAxis?: boolean;
}) {
  const lineTheme = LINE_CHART_THEME[useResolvedTheme()];
  const byName = new Map(series.map((s) => [s.name, s]));
  const tick = { fill: lineTheme.tick, fontSize: 10 };
  return (
    <div className="mt-3">
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 8, right: dualAxis ? 0 : 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={lineTheme.grid} />
          <XAxis
            dataKey="label"
            tick={tick}
            axisLine={{ stroke: lineTheme.grid }}
            tickLine={false}
          />
          {dualAxis ? (
            <>
              <YAxis
                yAxisId="left"
                width={38}
                domain={["auto", "auto"]}
                tick={tick}
                tickFormatter={fmtK}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                width={38}
                domain={["auto", "auto"]}
                tick={tick}
                tickFormatter={fmtK}
                axisLine={false}
                tickLine={false}
              />
            </>
          ) : (
            <YAxis
              width={38}
              domain={["auto", "auto"]}
              tick={tick}
              tickFormatter={fmtK}
              axisLine={false}
              tickLine={false}
            />
          )}
          <Tooltip
            {...tooltipStyles}
            cursor={{ stroke: lineTheme.grid }}
            formatter={(v, name) => [
              `${(byName.get(String(name))?.format ?? fmtKg1)(Number(v))} kg`,
              String(name),
            ]}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              {...(dualAxis ? { yAxisId: s.rightAxis ? "right" : "left" } : {})}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2}
              dot={{ r: 4, fill: s.color, stroke: lineTheme.dotStroke, strokeWidth: 2 }}
              activeDot={{ r: 5 }}
              connectNulls={s.connectNulls}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex gap-4">
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [mode, setMode] = useState<PeriodMode>("weekly");
  const [includeWarmup, setIncludeWarmup] = useState(false);
  const [selection, setSelection] = useState<ProgressSelection | null>(null);
  const [selectedBar, setSelectedBar] = useState<number | null>(null);
  const theme = useResolvedTheme();
  const lineTheme = LINE_CHART_THEME[theme];

  const today = todayStr();
  const periods = useMemo(() => buildPeriods(mode, today), [mode, today]);
  const from = mode === "weekly" ? periods[0] : `${periods[0]}-01`;
  const warmupParam = includeWarmup ? { include_warmup: true } : {};

  const summaryQ = useQuery({ queryKey: ["stats", "summary"], queryFn: fetchStatsSummary });
  const volumeQ = useQuery({
    queryKey: ["stats", "volume", mode, includeWarmup],
    queryFn: () =>
      fetchStatsVolume({ granularity: mode === "weekly" ? "week" : "month", from, ...warmupParam }),
    placeholderData: keepPreviousData,
  });
  const musclesQ = useQuery({
    queryKey: ["stats", "muscles", mode, includeWarmup],
    queryFn: () => fetchStatsMuscles({ from, ...warmupParam }),
    placeholderData: keepPreviousData,
  });
  const prsQ = useQuery({ queryKey: ["stats", "prs"], queryFn: fetchStatsPrs });

  // 기본값: 첫 PR 종목. 계열 선택 중에는 단일 종목 쿼리를 끈다.
  const familyBase = selection?.kind === "family" ? selection.base : null;
  const exerciseId =
    selection === null
      ? (prsQ.data?.records[0]?.exercise_id ?? null)
      : selection.kind === "exercise"
        ? selection.id
        : null;
  const exerciseQ = useQuery({
    queryKey: ["stats", "exercise", exerciseId, mode, includeWarmup],
    queryFn: () => fetchStatsExercise(exerciseId!, { from, ...warmupParam }),
    enabled: exerciseId !== null,
    placeholderData: keepPreviousData,
  });

  // §3.6 계열 드롭다운 재료: 같은 base_movement의 활성 종목 2개 이상일 때만 노출
  // (구현 결정, SETTING.MD §3.6 반영 — 1종뿐인 계열은 단일 종목 그래프와 동일해 항목만 늘린다)
  const exercisesQ = useQuery({ queryKey: ["exercises"], queryFn: () => fetchExercises() });
  const familyOptions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const ex of exercisesQ.data ?? []) {
      if (ex.base_movement) counts.set(ex.base_movement, (counts.get(ex.base_movement) ?? 0) + 1);
    }
    return [...counts.entries()]
      .filter(([, n]) => n >= 2)
      .map(([base]) => base)
      .sort((a, b) => a.localeCompare(b, "ko"));
  }, [exercisesQ.data]);

  const familyQ = useQuery({
    queryKey: ["stats", "family", familyBase],
    queryFn: () => fetchFamily(familyBase!),
    enabled: familyBase !== null,
    placeholderData: keepPreviousData,
  });

  const byPeriod = useMemo(() => {
    const m = new Map<string, VolumePoint>();
    for (const p of volumeQ.data?.points ?? []) m.set(p.period, p);
    return m;
  }, [volumeQ.data]);

  const volumeRows = useMemo(
    () =>
      periods.map((period) => ({
        label: periodLabel(mode, period),
        volume: Math.round(byPeriod.get(period)?.total_volume ?? 0),
      })),
    [periods, mode, byPeriod],
  );

  // 부위별 분배: 근육 단위 가중 볼륨을 region 6개로 합산, 볼륨 내림차순
  const regionDist = useMemo(() => {
    const sums = Object.fromEntries(REGION_ORDER.map((r) => [r, 0])) as Record<Region, number>;
    for (const p of musclesQ.data?.points ?? []) sums[p.region] += p.volume_kg;
    return REGION_ORDER.map((r) => ({ region: r, name: REGION_NAMES_KO[r], volume: sums[r] })).sort(
      (a, b) => b.volume - a.volume,
    );
  }, [musclesQ.data]);
  const maxRegion = Math.max(...regionDist.map((d) => d.volume), 1);
  const hasRegion = regionDist.some((d) => d.volume > 0);

  const exerciseRows = useMemo(
    () =>
      (exerciseQ.data?.points ?? []).map((p) => ({
        label: formatShortDate(p.date),
        top: p.top_weight_kg,
        e1rm: p.e1rm === null ? null : Math.round(p.e1rm * 10) / 10,
      })),
    [exerciseQ.data],
  );

  // 계열 합산 추이 — 서버는 전체 기간을 주므로 카드의 12주/12개월 범위로 클라이언트 필터
  const familyRows = useMemo(
    () =>
      (familyQ.data?.points ?? [])
        .filter((p) => p.date >= from)
        .map((p) => ({
          label: formatShortDate(p.date),
          volume: Math.round(p.total_volume),
          e1rm: p.top_e1rm === null ? null : Math.round(p.top_e1rm * 10) / 10,
        })),
    [familyQ.data, from],
  );
  const familyMembers = familyQ.data?.exercises.map((x) => x.name_ko).join(" · ") ?? "";

  const hasVolume = volumeRows.some((r) => r.volume > 0);
  const rangeNote = mode === "weekly" ? "12주" : "12개월";

  // 히어로 값: 현재 구간(마지막 바) — 차트와 동일 소스라 웜업 토글에도 항상 일치
  const heroValue = volumeRows[volumeRows.length - 1]?.volume ?? 0;
  // 변화율: 주간=서버 판정(change_pct, 전주 0이면 null), 월간=전월 대비 계산
  const heroChange = useMemo(() => {
    if (mode === "weekly") return summaryQ.data?.this_week.change_pct ?? null;
    const cur = volumeRows[volumeRows.length - 1]?.volume ?? 0;
    const prev = volumeRows[volumeRows.length - 2]?.volume ?? 0;
    return prev > 0 ? ((cur - prev) / prev) * 100 : null;
  }, [mode, summaryQ.data, volumeRows]);

  const changeEl =
    heroChange === null ? (
      <span className="font-bold text-hero-muted">—</span>
    ) : (
      <span className={`font-bold ${heroChange >= 0 ? "text-hero-accent" : "text-hero-danger"}`}>
        {heroChange >= 0 ? "▲" : "▼"} {Math.abs(heroChange).toFixed(1)}%
      </span>
    );

  const tw = summaryQ.data?.this_week;
  const statTiles = [
    { key: "sessions", label: "세션", value: tw ? fmtInt(tw.session_count) : "—" },
    { key: "sets", label: "세트", value: tw ? fmtInt(tw.set_count) : "—" },
    { key: "pr", label: "PR", value: tw ? fmtInt(tw.pr_count) : "—" },
  ] as const;

  const prFeed = prsQ.data?.feed.slice(0, 5) ?? [];

  return (
    <main className="mx-auto max-w-[720px] px-[18px] pt-4 pb-6">
      {/* 헤더: 다크 = "ANALYTICS" 레터스페이싱 타이틀 / 라이트 = "분석" */}
      <div className="flex items-center justify-between">
        <h1 className="hidden font-numeric text-[13px] font-medium tracking-[3px] text-muted dark:block">
          ANALYTICS
        </h1>
        <h1 className="text-[19px] font-extrabold dark:hidden">분석</h1>
        <div className="flex rounded-full bg-surface p-1 shadow-card dark:rounded-[9px] dark:p-0.5">
          {(["weekly", "monthly"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setSelectedBar(null);
              }}
              className={`rounded-full px-4 py-1.5 text-[13px] font-bold dark:rounded-[7px] ${
                mode === m ? "bg-hero text-hero-text dark:bg-bg dark:text-text" : "text-muted"
              }`}
            >
              {m === "weekly" ? "주간" : "월간"}
            </button>
          ))}
        </div>
      </div>

      <label className="mt-2 flex items-center justify-end gap-1.5 text-[11px] text-muted">
        <input
          type="checkbox"
          checked={includeWarmup}
          onChange={(e) => setIncludeWarmup(e.target.checked)}
          className="h-3.5 w-3.5 accent-accent"
        />
        웜업 포함
      </label>

      <div className="mt-3 space-y-3.5">
        {/* 히어로: 기간 볼륨 + 전 기간 대비 + 12구간 바 차트 (라이트=잉크 다크카드) */}
        <Card variant="hero" className={volumeQ.isPlaceholderData ? "opacity-60" : ""}>
          <div className="flex items-start justify-between">
            <p className="text-[13px] font-medium text-hero-muted">
              {mode === "weekly" ? "이번 주 볼륨" : "이번 달 볼륨"}
            </p>
            <span className="text-sm dark:hidden">{changeEl}</span>
          </div>
          <div className="mt-1.5 flex items-end gap-3">
            <p className="font-numeric text-[46px] leading-none font-bold tracking-[-1px] dark:text-[58px] dark:tracking-normal">
              {fmtInt(heroValue)}
              <span className="ml-1.5 text-sm font-medium tracking-normal text-hero-muted dark:hidden">
                kg
              </span>
            </p>
            <span className="hidden pb-1 text-[17px] dark:inline">{changeEl}</span>
          </div>
          {volumeQ.isPending ? (
            <Loading />
          ) : volumeQ.isError ? (
            <div className="flex flex-col items-center gap-3 py-6">
              <p className="text-sm text-hero-muted">불러오지 못했습니다</p>
              <button
                type="button"
                onClick={() => volumeQ.refetch()}
                className="touch-target rounded-field px-4 text-sm font-bold text-hero-accent"
              >
                다시 시도
              </button>
            </div>
          ) : !hasVolume ? (
            <p className="py-8 text-center text-sm text-hero-muted">아직 기록이 없습니다</p>
          ) : (
            <HeroBarChart rows={volumeRows} selected={selectedBar} onSelect={setSelectedBar} />
          )}
        </Card>

        {/* 요약 스탯 3칸 — PR 칸 강조 (이번 주 기준) */}
        <div className="grid grid-cols-3 gap-3">
          {statTiles.map((t) => (
            <Card
              key={t.key}
              className={
                t.key === "pr" ? "dark:bg-[linear-gradient(160deg,#2a1510,#171512)]" : ""
              }
            >
              <p
                className={`text-[11px] font-medium ${t.key === "pr" ? "font-bold text-pr" : "text-muted"}`}
              >
                {t.label}
              </p>
              <p
                className={`mt-1.5 font-numeric text-[26px] leading-none font-semibold ${
                  t.key === "pr" ? "dark:text-accent" : ""
                }`}
              >
                {t.value}
              </p>
            </Card>
          ))}
        </div>

        {/* 부위별 분배 — region 6개(코어 포함), 볼륨순 램프 */}
        <Card className={musclesQ.isPlaceholderData ? "opacity-60" : ""}>
          <CardTitle title="부위별 분배" note={rangeNote} />
          {musclesQ.isPending ? (
            <Loading />
          ) : musclesQ.isError ? (
            <ErrorRetry onRetry={() => musclesQ.refetch()} />
          ) : !hasRegion ? (
            <EmptyNote text="아직 기록이 없습니다" />
          ) : (
            <div className="space-y-3">
              {regionDist.map((d, i) => (
                <div key={d.region} className="flex items-center gap-3">
                  <span className="w-[34px] shrink-0 text-sm font-medium">{d.name}</span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-track-soft dark:h-3 dark:rounded-[3px]">
                    <div
                      className="h-full rounded-full dark:rounded-[3px]"
                      style={{
                        width: `${(d.volume / maxRegion) * 100}%`,
                        background: i < 5 ? RAMP_VARS[i] : RAMP_6[theme],
                      }}
                    />
                  </div>
                  <span className="w-10 shrink-0 text-right font-numeric text-[13px] font-medium text-muted">
                    {fmtK(d.volume)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 최근 PR — 종목명 + 종류·날짜 캡션 + 기록값 */}
        <Card>
          {prsQ.isPending ? (
            <Loading />
          ) : prsQ.isError ? (
            <ErrorRetry onRetry={() => prsQ.refetch()} />
          ) : prFeed.length === 0 ? (
            <EmptyNote text="아직 PR이 없습니다 — 첫 기록은 베이스라인입니다" />
          ) : (
            <ul className="divide-y divide-hairline">
              {prFeed.map((pr, i) => (
                <li
                  key={`${pr.date}-${pr.exercise_id}-${pr.kind}-${i}`}
                  className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[15px] font-bold">{pr.exercise_name_ko}</p>
                    <p className="mt-0.5 text-[11px] font-medium text-muted dark:text-accent">
                      {pr.kind === "weight" ? "중량" : "e1RM"} PR · {formatShortDate(pr.date)}
                    </p>
                  </div>
                  <p className="ml-3 shrink-0 font-numeric text-[22px] font-bold">
                    {fmtKg1(pr.value)}{" "}
                    <span className="text-[12px] font-medium text-muted dark:uppercase">kg</span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* 종목별 진행 — 시안 외 기존 기능 유지(토큰 재스킨). §3.6: 계열 합산 항목 추가 */}
        <Card
          className={
            (familyBase !== null ? familyQ.isPlaceholderData : exerciseQ.isPlaceholderData)
              ? "opacity-60"
              : ""
          }
        >
          <CardTitle
            title="종목별 진행"
            note={
              familyBase !== null
                ? "계열 합산 · 웜업 제외"
                : includeWarmup
                  ? "웜업 포함"
                  : "웜업 제외"
            }
          />
          {prsQ.isPending ? (
            <Loading />
          ) : prsQ.isError ? (
            <ErrorRetry onRetry={() => prsQ.refetch()} />
          ) : prsQ.data.records.length === 0 ? (
            <EmptyNote text="아직 기록된 종목이 없습니다" />
          ) : (
            <>
              <select
                value={familyBase !== null ? `${FAMILY_PREFIX}${familyBase}` : (exerciseId ?? "")}
                onChange={(e) => {
                  const v = e.target.value;
                  setSelection(
                    v.startsWith(FAMILY_PREFIX)
                      ? { kind: "family", base: v.slice(FAMILY_PREFIX.length) }
                      : { kind: "exercise", id: Number(v) },
                  );
                }}
                className="touch-target w-full rounded-[10px] border border-line bg-well px-3 text-sm"
              >
                {prsQ.data.records.map((r) => (
                  <option key={r.exercise_id} value={r.exercise_id}>
                    {r.name_ko}
                  </option>
                ))}
                {familyOptions.length > 0 && (
                  <optgroup label="계열 합산">
                    {familyOptions.map((base) => (
                      <option key={base} value={`${FAMILY_PREFIX}${base}`}>
                        {base} (계열)
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>

              {familyBase !== null ? (
                familyQ.isPending ? (
                  <Loading />
                ) : familyQ.isError ? (
                  <ErrorRetry onRetry={() => familyQ.refetch()} />
                ) : familyRows.length === 0 ? (
                  <EmptyNote text="이 기간에는 기록이 없습니다" />
                ) : (
                  <>
                    {/* 합산 볼륨(좌축)과 e1RM(우축)은 스케일이 달라 이중 축 */}
                    <TrendLineChart
                      data={familyRows}
                      dualAxis
                      series={[
                        { key: "volume", name: "합산 볼륨", color: lineTheme.top, format: fmtInt },
                        {
                          key: "e1rm",
                          name: "Top e1RM",
                          color: lineTheme.e1rm,
                          rightAxis: true,
                          connectNulls: true,
                        },
                      ]}
                    />
                    {/* 참여 종목 캡션 — 어떤 행들이 합산됐는지 항상 드러낸다 (§3.6 불변식: 정체성=행) */}
                    {familyMembers && (
                      <p className="mt-3 text-[11px] leading-relaxed text-muted">
                        참여 종목: {familyMembers}
                      </p>
                    )}
                  </>
                )
              ) : exerciseQ.isPending ? (
                <Loading />
              ) : exerciseQ.isError ? (
                <ErrorRetry onRetry={() => exerciseQ.refetch()} />
              ) : exerciseRows.length === 0 ? (
                <EmptyNote text="이 기간에는 기록이 없습니다" />
              ) : (
                <>
                  <TrendLineChart
                    data={exerciseRows}
                    series={[
                      { key: "top", name: "Top 중량", color: lineTheme.top },
                      { key: "e1rm", name: "e1RM", color: lineTheme.e1rm, connectNulls: true },
                    ]}
                  />

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    {(
                      [
                        { label: "중량 PR", pr: exerciseQ.data.weight_pr },
                        { label: "e1RM PR", pr: exerciseQ.data.e1rm_pr },
                      ] as const
                    ).map(({ label, pr }) => (
                      <div key={label} className="rounded-[10px] bg-well p-3">
                        <p className="text-[11px] text-muted">{label}</p>
                        {pr ? (
                          <>
                            <p className="mt-0.5 font-numeric text-lg font-semibold">
                              {fmtKg1(pr.value)}{" "}
                              <span className="text-xs font-normal text-muted">kg</span>
                            </p>
                            <p className="text-[11px] text-muted">
                              {fmtKg1(pr.weight_kg)}kg × {pr.reps} · {formatKoreanDate(pr.date)}
                            </p>
                          </>
                        ) : (
                          <p className="mt-0.5 text-sm text-muted">기록 없음</p>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </Card>
      </div>
    </main>
  );
}
