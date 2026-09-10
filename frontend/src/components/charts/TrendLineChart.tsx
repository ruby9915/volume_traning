// 대시보드 라인차트 공용 — 종목별 진행·계열 합산(Dashboard)과 고급 분석 볼륨 추세가 같은
// 스타일(그리드·축·점·범례)을 공유한다. Dashboard.tsx에서 분리(§11).
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useResolvedTheme } from "../../theme";
import { fmtK, fmtKg1 } from "../../utils/format";

/**
 * recharts는 색을 SVG presentation attribute로 내보내는데, attribute에서는
 * var()가 해석되지 않아 토큰 값을 hex로 미러링한다 (index.css @theme와 동기).
 */
export const LINE_CHART_THEME = {
  light: { grid: "#e3e7e1", tick: "#71806f", top: "#0fa96f", e1rm: "#9aa89a", dotStroke: "#ffffff" },
  dark: { grid: "#2a2620", tick: "#8a8378", top: "#ff4a1f", e1rm: "#8a8378", dotStroke: "#171512" },
} as const;

export const tooltipStyles = {
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

export interface TrendSeries {
  key: string;
  name: string;
  color: string;
  /** 이중 축(dualAxis)일 때 우축에 붙일 시리즈 */
  rightAxis?: boolean;
  /** null 구간을 이어 그린다 (e1RM은 reps>12 세션에서 null) */
  connectNulls?: boolean;
  /** 툴팁 값 포맷 — 기본 소수 1자리 */
  format?: (v: number) => string;
  /** 점선 (이동평균 같은 파생 시리즈) */
  dashed?: boolean;
  /** 점 숨김 */
  noDot?: boolean;
}

/**
 * dualAxis: 좌축(볼륨)과 우축(e1RM)처럼 스케일이 다른 시리즈를 한 차트에 그릴 때.
 * unit: 툴팁 단위 표기 (기본 kg).
 */
export default function TrendLineChart({
  data,
  series,
  dualAxis = false,
  unit = "kg",
  height = 200,
}: {
  data: Record<string, string | number | null>[];
  series: TrendSeries[];
  dualAxis?: boolean;
  unit?: string;
  height?: number;
}) {
  const lineTheme = LINE_CHART_THEME[useResolvedTheme()];
  const byName = new Map(series.map((s) => [s.name, s]));
  const tick = { fill: lineTheme.tick, fontSize: 10 };
  return (
    <div className="mt-3">
      <ResponsiveContainer width="100%" height={height}>
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
              `${(byName.get(String(name))?.format ?? fmtKg1)(Number(v))} ${unit}`,
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
              strokeDasharray={s.dashed ? "4 3" : undefined}
              dot={s.noDot ? false : { r: 4, fill: s.color, stroke: lineTheme.dotStroke, strokeWidth: 2 }}
              activeDot={{ r: 5 }}
              connectNulls={s.connectNulls}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex gap-4">
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1.5 text-[11px] text-muted">
            <span
              className="inline-block h-0.5 w-3 rounded"
              style={{
                backgroundColor: s.dashed ? "transparent" : s.color,
                borderTop: s.dashed ? `2px dashed ${s.color}` : undefined,
              }}
            />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}
