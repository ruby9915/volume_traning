// §13 친구 세션 읽기 전용 뷰 — 종목별 세트 나열만. 편집 화면(SessionDetail)의 조작은 전혀 없다.
import { useQuery } from "@tanstack/react-query";
import { fetchSession } from "../../api/client";
import { TECHNIQUE_NAMES_KO } from "../../api/types";
import { useTargets } from "../../hooks/useTargets";
import { formatKoreanDate } from "../../utils/date";
import { fmtInt } from "../../utils/format";
import Card from "../Card";
import ErrorRetry from "../ErrorRetry";
import Spinner from "../Spinner";

export default function ReadOnlySession({ sessionId, userId }: { sessionId: number; userId: number }) {
  const { nameOf } = useTargets();
  const q = useQuery({
    queryKey: ["u", userId, "session", sessionId],
    queryFn: () => fetchSession(sessionId, userId),
  });
  if (q.isPending)
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  if (q.isError) return <ErrorRetry onRetry={() => q.refetch()} />;
  const s = q.data;
  return (
    <Card>
      <p className="font-numeric text-xs font-semibold text-muted">{formatKoreanDate(s.date)}</p>
      <p className="mt-1 font-numeric text-sm">
        세트 {fmtInt(s.set_count)} · 볼륨 {fmtInt(Math.round(s.total_volume))}kg
      </p>
      {s.note ? <p className="mt-1 text-sm text-muted">{s.note}</p> : null}
      <div className="mt-3 flex flex-col gap-3">
        {s.exercises.map((g) => (
          <div key={g.exercise_id}>
            <div className="flex items-baseline justify-between">
              <span className="font-semibold">{g.name_ko}</span>
              <span className="font-numeric text-xs text-muted">{g.sets.length}세트</span>
            </div>
            <p className="mt-0.5 font-numeric text-sm text-muted">
              {g.sets
                .map((x) => `${x.is_warmup ? "W " : ""}${x.technique ? `[${TECHNIQUE_NAMES_KO[x.technique]}] ` : ""}${x.weight_kg}×${x.reps}${x.target !== g.default_target ? `(${nameOf(x.target)})` : ""}`)
                .join(" · ")}
            </p>
          </div>
        ))}
        {s.exercises.length === 0 ? <p className="text-sm text-muted">세트 없음</p> : null}
      </div>
    </Card>
  );
}
