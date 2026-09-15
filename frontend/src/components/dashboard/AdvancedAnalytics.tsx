// §11 고급 분석 섹션 — 대시보드 하단. 데이터 준비도 게이트(훈련 4주 미만)면 잠금 카드 하나만.
// 서버(/api/stats/advanced/*)가 403 insufficient_data로 막으므로 여기의 잠금은 안내일 뿐 우회 불가.
import { useState, type ReactNode } from "react";
import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  fetchAdvancedFrequency,
  fetchAdvancedTrend,
  fetchAttribution,
  fetchFatigue,
  fetchIntensity,
  fetchRepMax,
  insufficientDataOf,
} from "../../api/client";
import type { AnalyticsGate, BucketShare, MuscleWeekFrequency } from "../../api/types";
import { useAppStore } from "../../store";
import { useSubject } from "../../subject";
import { useResolvedTheme } from "../../theme";
import { formatShortDate } from "../../utils/date";
import { fmtInt, fmtK, fmtKg1, fmtWeight } from "../../utils/format";
import Card from "../Card";
import ErrorRetry from "../ErrorRetry";
import Spinner from "../Spinner";
import TrendLineChart, { LINE_CHART_THEME } from "../charts/TrendLineChart";

const RAMP = (n: number) => `var(--color-ramp-${n})`;
const FREQUENCY_WEEKS = 8;
const TREND_WEEKS = 16;

// ---------- 공용 소품 ----------

function CardTitle({ title, note }: { title: string; note?: string }) {
  return (
    <div className="mb-3 flex items-baseline gap-1.5">
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

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { key: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex shrink-0 rounded-full bg-well p-0.5 dark:rounded-[7px]">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          onClick={() => onChange(o.key)}
          className={`rounded-full px-2.5 py-1 text-[11px] font-semibold dark:rounded-[6px] ${
            value === o.key ? "bg-surface text-text shadow-card" : "text-muted"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** 쿼리 상태 공통 처리 — 게이트 403은 에러가 아니라 잠금 안내 */
function Status<T>({
  q,
  render,
  isEmpty,
  emptyText = "아직 기록이 없습니다",
}: {
  q: UseQueryResult<T>;
  render: (d: T) => ReactNode;
  isEmpty?: (d: T) => boolean;
  emptyText?: string;
}) {
  if (q.isPending) return <Loading />;
  if (q.isError) {
    const locked = insufficientDataOf(q.error);
    if (locked) {
      return <EmptyNote text={`훈련 ${locked.weeks_of_data}/${locked.required_weeks}주 — 아직 잠겨 있습니다`} />;
    }
    return <ErrorRetry onRetry={() => q.refetch()} />;
  }
  if (isEmpty?.(q.data)) return <EmptyNote text={emptyText} />;
  return <>{render(q.data)}</>;
}

/** 구간 분포 스택 바 + 범례 (강도 존·rep range 공용) */
function StackedBar({ buckets, colors }: { buckets: BucketShare[]; colors: string[] }) {
  const total = buckets.reduce((s, b) => s + b.sets, 0);
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-track-soft dark:rounded-[3px]">
        {buckets.map((b, i) =>
          b.sets > 0 ? (
            <div
              key={b.bucket}
              style={{ width: `${(b.sets / Math.max(total, 1)) * 100}%`, background: colors[i] }}
              title={`${b.bucket}: ${b.sets}세트`}
            />
          ) : null,
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {buckets.map((b, i) => (
          <span key={b.bucket} className="flex items-center gap-1 text-[11px] text-muted">
            <span className="inline-block h-2 w-2 rounded-[2px]" style={{ background: colors[i] }} />
            {b.bucket} <span className="font-numeric">{Math.round(b.share * 100)}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------- 잠금 카드 ----------

function LockedCard({ gate }: { gate: AnalyticsGate }) {
  const pct = Math.min(100, (gate.weeks_of_data / gate.required_weeks) * 100);
  return (
    <Card>
      <div className="flex items-baseline justify-between">
        <CardTitle title="고급 분석" note="잠김" />
        <span className="font-numeric text-sm font-bold">
          {gate.weeks_of_data}/{gate.required_weeks}주
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-track-soft dark:rounded-[3px]">
        <div className="h-full rounded-full bg-accent dark:rounded-[3px]" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        웜업이 아닌 세트가 기록된 주가 {gate.required_weeks}주 이상 쌓이면 열립니다 — 분할 실행 점검 ·
        볼륨 추세(4주 이동평균·ACWR) · 관여 근육 분배(간접 볼륨) · rep-max 매트릭스 · 세트 내 피로 곡선 ·
        강도 존 분포. 짧은 데이터로는 평균과 추세가 잡음이라 막아 둡니다.
      </p>
    </Card>
  );
}

// ---------- 1. 분할 실행 점검 ----------

function cellColor(n: number): string {
  if (n <= 0) return "var(--color-track-soft)";
  if (n === 1) return RAMP(4);
  if (n === 2) return RAMP(2);
  return RAMP(1);
}

function FrequencyCard() {
  const [level, setLevel] = useState<"region" | "muscle">("region");
  const { userId } = useSubject();
  const q = useQuery({
    queryKey: ["stats", "advanced", "frequency", FREQUENCY_WEEKS, userId],
    queryFn: () => fetchAdvancedFrequency(FREQUENCY_WEEKS, userId),
  });
  return (
    <Card>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <CardTitle title="분할 실행 점검" note={`${FREQUENCY_WEEKS}주 · 주별 세션 수`} />
        <Segmented
          value={level}
          onChange={setLevel}
          options={[
            { key: "region", label: "부위" },
            { key: "muscle", label: "근육" },
          ]}
        />
      </div>
      <Status
        q={q}
        isEmpty={(d) => (level === "region" ? d.regions : d.muscles).every((r) => r.days_since_last === null)}
        render={(d) => {
          // 한 번도 자극하지 않은 부위는 방치가 아니라 '해당 없음' — 표에서 뺀다
          const rows: MuscleWeekFrequency[] = (level === "region" ? d.regions : d.muscles).filter(
            (r) => r.days_since_last !== null,
          );
          const neglected = rows.filter((r) => r.neglected);
          const n = d.weeks.length;
          return (
            <>
              <div className="flex items-center gap-2 text-[9px] text-faint">
                <span className="w-[64px] shrink-0" />
                <div className="flex flex-1 justify-between">
                  <span>{formatShortDate(d.weeks[0])}</span>
                  <span>{formatShortDate(d.weeks[Math.floor(n / 2)])}</span>
                  <span>이번 주</span>
                </div>
                <span className="w-[52px] shrink-0" />
              </div>
              <div className="mt-1.5 space-y-1.5">
                {rows.map((r) => (
                  <div key={r.code} className="flex items-center gap-2">
                    <span className="w-[64px] shrink-0 truncate text-[13px] font-medium">{r.name_ko}</span>
                    <div className="flex flex-1 gap-1">
                      {r.per_week.map((c, i) => (
                        <span
                          key={i}
                          className="h-5 flex-1 rounded-[4px]"
                          style={{ background: cellColor(c) }}
                          title={`${formatShortDate(d.weeks[i])} 주 ${c}회`}
                        />
                      ))}
                    </div>
                    <span className="w-[52px] shrink-0 text-right font-numeric text-[11px] text-muted">
                      {r.neglected ? (
                        <span className="font-semibold text-danger">{r.days_since_last}일 전</span>
                      ) : (
                        `${r.avg_per_week.toFixed(1)}/주`
                      )}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
                {[0, 1, 2, 3].map((c) => (
                  <span key={c} className="flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: cellColor(c) }} />
                    {c === 3 ? "3회+" : `${c}회`}
                  </span>
                ))}
                <span className="ml-auto">오른쪽: 완료 주 평균 (이번 주 제외)</span>
              </div>
              {neglected.length > 0 ? (
                <p className="mt-2 text-xs text-danger">
                  방치({d.neglect_days}일+): {neglected.map((r) => `${r.name_ko} ${r.days_since_last}일`).join(" · ")}
                </p>
              ) : null}
            </>
          );
        }}
      />
    </Card>
  );
}

// ---------- 2. 볼륨 추세 (4주 이동평균 · ACWR) ----------

function TrendCard() {
  const lineTheme = LINE_CHART_THEME[useResolvedTheme()];
  const { userId } = useSubject();
  const q = useQuery({
    queryKey: ["stats", "advanced", "trend", TREND_WEEKS, userId],
    queryFn: () => fetchAdvancedTrend(TREND_WEEKS, userId),
  });
  return (
    <Card>
      <CardTitle title="볼륨 추세" note={`${TREND_WEEKS}주 · 웜업 제외`} />
      <Status
        q={q}
        isEmpty={(d) => d.first_week === null}
        render={(d) => {
          const rows = d.points.map((p) => ({
            label: formatShortDate(p.week_start),
            volume: Math.round(p.volume_kg),
            ma4: p.ma4_kg === null ? null : Math.round(p.ma4_kg),
          }));
          const current = d.points[d.points.length - 1];
          // ACWR 판정은 완료된 주만 — 진행 중인 주는 분자가 아직 작아 항상 과소
          const completed = [...d.points].reverse().find((p) => !p.in_progress && p.acwr !== null) ?? null;
          const warn = completed !== null && completed.acwr !== null && completed.acwr > d.acwr_warn;
          return (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-[10px] bg-well p-3">
                  <p className="text-[11px] text-muted">이번 주</p>
                  <p className="mt-0.5 font-numeric text-lg font-semibold">{fmtK(current?.volume_kg ?? 0)}</p>
                  <p className="text-[10px] text-faint">진행 중</p>
                </div>
                <div className="rounded-[10px] bg-well p-3">
                  <p className="text-[11px] text-muted">4주 평균</p>
                  <p className="mt-0.5 font-numeric text-lg font-semibold">
                    {current?.ma4_kg == null ? "—" : fmtK(current.ma4_kg)}
                  </p>
                  <p className="text-[10px] text-faint">이번 주 포함</p>
                </div>
                <div className={`rounded-[10px] p-3 ${warn ? "bg-danger/10" : "bg-well"}`}>
                  <p className={`text-[11px] ${warn ? "font-bold text-danger" : "text-muted"}`}>ACWR</p>
                  <p className={`mt-0.5 font-numeric text-lg font-semibold ${warn ? "text-danger" : ""}`}>
                    {completed?.acwr == null ? "—" : completed.acwr.toFixed(2)}
                  </p>
                  <p className="text-[10px] text-faint">
                    {completed ? `${formatShortDate(completed.week_start)} 주` : "완료 주 4+ 필요"}
                  </p>
                </div>
              </div>
              {warn ? (
                <p className="mt-2 text-xs text-danger">
                  직전 완료 주 볼륨이 그 전 4주 평균의 {d.acwr_warn}배를 넘었습니다 — 급증 구간입니다.
                </p>
              ) : null}
              <TrendLineChart
                data={rows}
                series={[
                  { key: "volume", name: "주간 볼륨", color: lineTheme.top, format: fmtInt },
                  {
                    key: "ma4",
                    name: "4주 이동평균",
                    color: lineTheme.e1rm,
                    dashed: true,
                    noDot: true,
                    connectNulls: true,
                    format: fmtInt,
                  },
                ]}
              />
              <p className="mt-2 text-[11px] leading-relaxed text-muted">
                ACWR = 그 주 볼륨 ÷ 직전 4주 평균. 쉰 주는 0으로 평균에 들어갑니다. 첫 훈련 주 이전 구간이
                걸리면 값 없음.
              </p>
            </>
          );
        }}
      />
    </Card>
  );
}

// ---------- 3. 관여 근육 분배 (직접 + 간접) ----------

function AttributionCard({
  from,
  includeWarmup,
  rangeNote,
}: {
  from: string;
  includeWarmup: boolean;
  rangeNote: string;
}) {
  const weight = useAppStore((s) => s.indirectWeight);
  const [unit, setUnit] = useState<"sets" | "volume">("sets");
  const { userId } = useSubject();
  const q = useQuery({
    queryKey: ["stats", "advanced", "attribution", from, includeWarmup, weight, userId],
    queryFn: () =>
      fetchAttribution({
        from,
        ...(includeWarmup ? { include_warmup: true } : {}),
        indirect_weight: weight,
        user_id: userId,
      }),
    placeholderData: keepPreviousData,
  });
  return (
    <Card className={q.isPlaceholderData ? "opacity-60" : ""}>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <CardTitle title="관여 근육 분배" note={`${rangeNote} · 간접 ×${weight}`} />
        <Segmented
          value={unit}
          onChange={setUnit}
          options={[
            { key: "sets", label: "세트" },
            { key: "volume", label: "볼륨" },
          ]}
        />
      </div>
      <Status
        q={q}
        isEmpty={(d) => d.points.every((p) => p.fractional_sets === 0)}
        render={(d) => {
          const pick = (p: (typeof d.points)[number]) =>
            unit === "sets"
              ? { direct: p.direct_sets, total: p.fractional_sets }
              : { direct: p.direct_volume_kg, total: p.fractional_volume_kg };
          const rows = d.points
            .map((p) => ({ code: p.code, name: p.name_ko, ...pick(p) }))
            .filter((r) => r.total > 0)
            .sort((a, b) => b.total - a.total)
            .slice(0, 12);
          const max = Math.max(...rows.map((r) => r.total), 1);
          const fmt = unit === "sets" ? (v: number) => fmtKg1(v) : fmtK;
          return (
            <>
              <div className="space-y-2.5">
                {rows.map((r) => {
                  const indirect = r.total - r.direct;
                  return (
                    <div key={r.code} className="flex items-center gap-3">
                      <span className="w-[64px] shrink-0 truncate text-[13px] font-medium">{r.name}</span>
                      <div className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-track-soft dark:h-3 dark:rounded-[3px]">
                        <div style={{ width: `${(r.direct / max) * 100}%`, background: RAMP(1) }} />
                        <div style={{ width: `${(indirect / max) * 100}%`, background: RAMP(4) }} />
                      </div>
                      <span className="w-[74px] shrink-0 text-right font-numeric text-[12px] text-muted">
                        {fmt(r.direct)}
                        {indirect > 0 ? <span className="text-faint"> +{fmt(indirect)}</span> : null}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-[2px]" style={{ background: RAMP(1) }} />
                  직접 (세트 타겟 100% — 메인과 동일)
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-[2px]" style={{ background: RAMP(4) }} />
                  간접 (보조 근육 × {d.indirect_weight})
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-muted">
                간접은 보조 데이터입니다 — 총볼륨·PR·부위별 분배에는 더하지 않습니다. 보조 근육은 종목
                편집에서, 가중치는 설정에서 바꿉니다.
              </p>
            </>
          );
        }}
      />
    </Card>
  );
}

// ---------- 4. rep-max 매트릭스 + Rep PR ----------

function RepMaxCard({ exerciseId }: { exerciseId: number | null }) {
  const { userId } = useSubject();
  const q = useQuery({
    queryKey: ["stats", "advanced", "rep-max", exerciseId, userId],
    queryFn: () => fetchRepMax(exerciseId!, userId),
    enabled: exerciseId !== null,
    placeholderData: keepPreviousData,
  });
  if (exerciseId === null) {
    return (
      <Card>
        <CardTitle title="rep-max 매트릭스" />
        <EmptyNote text="아직 기록된 종목이 없습니다" />
      </Card>
    );
  }
  return (
    <Card className={q.isPlaceholderData ? "opacity-60" : ""}>
      <CardTitle title="rep-max 매트릭스" note={q.data ? `${q.data.name_ko} · 전체 기간` : undefined} />
      <Status
        q={q}
        isEmpty={(d) => d.cells.every((c) => c.implied_weight_kg === null)}
        emptyText="중량 기록이 없습니다 (맨몸 세트는 제외)"
        render={(d) => (
          <>
            <div className="grid grid-cols-4 gap-2">
              {d.cells.map((c) => {
                const showImplied =
                  c.implied_weight_kg !== null &&
                  (c.best_weight_kg === null || c.implied_weight_kg > c.best_weight_kg);
                return (
                  <div key={c.reps} className="rounded-[10px] bg-well p-2 text-center">
                    <p className="text-[10px] text-muted">{c.reps}RM</p>
                    <p className={`font-numeric text-[15px] font-semibold ${c.best_weight_kg === null ? "text-faint" : ""}`}>
                      {c.best_weight_kg === null ? "—" : fmtWeight(c.best_weight_kg)}
                    </p>
                    <p className="h-3 text-[10px] text-faint">
                      {showImplied ? `≥ ${fmtWeight(c.implied_weight_kg!)}` : ""}
                    </p>
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted">
              굵은 값 = 정확히 그 횟수로 든 최고 중량. ≥ = 그 횟수 이상으로 든 최고 중량(더 무겁게 더 많이 한
              기록이 있으면 표시).
            </p>
            {d.rep_prs.length > 0 ? (
              <>
                <p className="mt-3 mb-1 text-[11px] font-semibold text-muted">Rep PR · 같은 중량으로 더 많이</p>
                <ul className="divide-y divide-hairline">
                  {d.rep_prs.slice(0, 5).map((e, i) => (
                    <li key={`${e.date}-${e.weight_kg}-${i}`} className="flex items-center justify-between py-2">
                      <span className="text-[13px]">
                        <span className="font-numeric font-semibold">{fmtWeight(e.weight_kg)}kg × {e.reps}</span>
                        <span className="ml-1.5 text-[11px] text-muted">이전 {e.prev_reps}회</span>
                      </span>
                      <span className="font-numeric text-[11px] text-muted">{formatShortDate(e.date)}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="mt-3 text-[11px] text-muted">Rep PR 없음 — 같은 중량의 첫 세션은 베이스라인입니다.</p>
            )}
          </>
        )}
      />
    </Card>
  );
}

// ---------- 5. 세트 내 피로 곡선 + rep range (종목) ----------

const REP_RANGE_COLORS = [RAMP(1), RAMP(2), RAMP(3), RAMP(4)];

function FatigueCard({ exerciseId, from, rangeNote }: { exerciseId: number | null; from: string; rangeNote: string }) {
  const { userId } = useSubject();
  const q = useQuery({
    queryKey: ["stats", "advanced", "fatigue", exerciseId, from, userId],
    queryFn: () => fetchFatigue(exerciseId!, { from, user_id: userId }),
    enabled: exerciseId !== null,
    placeholderData: keepPreviousData,
  });
  if (exerciseId === null) {
    return (
      <Card>
        <CardTitle title="세트 내 피로 곡선" />
        <EmptyNote text="아직 기록된 종목이 없습니다" />
      </Card>
    );
  }
  return (
    <Card className={q.isPlaceholderData ? "opacity-60" : ""}>
      <CardTitle
        title="세트 내 피로 곡선"
        note={q.data ? `${q.data.name_ko} · ${rangeNote} · 세션 ${q.data.sessions_used}회` : rangeNote}
      />
      <Status
        q={q}
        isEmpty={(d) => d.points.length === 0}
        emptyText="이 기간에는 워킹 세트가 없습니다"
        render={(d) => {
          const max = Math.max(...d.points.map((p) => p.avg_reps), 1);
          return (
            <>
              <div className="space-y-2">
                {d.points.map((p) => (
                  <div key={p.ordinal} className="flex items-center gap-3">
                    <span className="w-[40px] shrink-0 text-[12px] font-medium text-muted">{p.ordinal}세트</span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-track-soft dark:h-3 dark:rounded-[3px]">
                      <div
                        className="h-full rounded-full dark:rounded-[3px]"
                        style={{ width: `${(p.avg_reps / max) * 100}%`, background: RAMP(Math.min(p.ordinal, 5)) }}
                      />
                    </div>
                    <span className="w-[92px] shrink-0 text-right font-numeric text-[12px]">
                      {p.avg_reps.toFixed(1)}회
                      <span className="text-muted"> · {p.rel_reps === null ? "—" : `${Math.round(p.rel_reps * 100)}%`}</span>
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-muted">
                평균 횟수 · 1세트 대비 비율. 뒷세트로 갈수록 급락하면 휴식 부족 또는 첫 세트가 너무 무거운
                신호입니다(세션 수가 적으면 해석 보류).
              </p>
              <p className="mt-3 mb-1.5 text-[11px] font-semibold text-muted">rep range 분포 (이 종목)</p>
              <StackedBar buckets={d.rep_ranges} colors={REP_RANGE_COLORS} />
            </>
          );
        }}
      />
    </Card>
  );
}

// ---------- 6. 강도 존 분포 (전체) ----------

const ZONE_COLORS = [RAMP(5), RAMP(4), RAMP(3), RAMP(2), RAMP(1)];

function IntensityCard({ from, rangeNote }: { from: string; rangeNote: string }) {
  const { userId } = useSubject();
  const q = useQuery({
    queryKey: ["stats", "advanced", "intensity", from, userId],
    queryFn: () => fetchIntensity({ from, user_id: userId }),
    placeholderData: keepPreviousData,
  });
  return (
    <Card className={q.isPlaceholderData ? "opacity-60" : ""}>
      <CardTitle title="강도 존 분포" note={`${rangeNote} · 전 종목 · %e1RM`} />
      <Status
        q={q}
        isEmpty={(d) => d.sets_total === 0 && d.rep_ranges.every((b) => b.sets === 0)}
        render={(d) => (
          <>
            <div className="mb-3 flex items-baseline gap-2">
              <p className="font-numeric text-[26px] leading-none font-semibold">
                {d.avg_intensity_pct === null ? "—" : `${d.avg_intensity_pct.toFixed(0)}%`}
              </p>
              <p className="text-[11px] text-muted">평균 강도 · 세트 {fmtInt(d.sets_total)}</p>
            </div>
            <StackedBar buckets={d.zones} colors={ZONE_COLORS} />
            <p className="mt-2 text-[11px] leading-relaxed text-muted">
              강도 = 세트 중량 ÷ 그 시점까지 그 종목의 최고 e1RM. 맨몸 세트와 e1RM이 아직 없는 종목의 세트는
              제외됩니다.
            </p>
            <p className="mt-3 mb-1.5 text-[11px] font-semibold text-muted">rep range 분포 (워킹 세트 전체)</p>
            <StackedBar buckets={d.rep_ranges} colors={REP_RANGE_COLORS} />
          </>
        )}
      />
    </Card>
  );
}

// ---------- 섹션 ----------

export default function AdvancedAnalytics({
  gate,
  exerciseId,
  from,
  includeWarmup,
  rangeNote,
}: {
  gate: AnalyticsGate | undefined;
  /** 종목별 카드(rep-max·피로 곡선)의 대상 — 대시보드 '종목별 진행' 선택과 같다 */
  exerciseId: number | null;
  from: string;
  includeWarmup: boolean;
  rangeNote: string;
}) {
  if (!gate) return null;
  if (!gate.ready) return <LockedCard gate={gate} />;
  return (
    <>
      <div className="mt-2 flex items-baseline gap-1.5 px-1">
        <h2 className="text-[12px] font-bold tracking-wide text-muted uppercase">고급 분석</h2>
        <span className="text-[11px] text-faint">· 훈련 {gate.weeks_of_data}주</span>
      </div>
      <FrequencyCard />
      <TrendCard />
      <AttributionCard from={from} includeWarmup={includeWarmup} rangeNote={rangeNote} />
      <RepMaxCard exerciseId={exerciseId} />
      <FatigueCard exerciseId={exerciseId} from={from} rangeNote={rangeNote} />
      <IntensityCard from={from} rangeNote={rangeNote} />
    </>
  );
}
