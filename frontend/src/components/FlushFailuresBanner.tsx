import { useEffect, useState } from "react";
import { dismissFlushFailures, subscribeFlushFailures } from "../api/client";
import type { FlushFailure } from "../api/client";
import type { Exercise } from "../api/types";
import { fmtWeight } from "../utils/format";
import Button from "./Button";
import Card from "./Card";

// §5.4 silent 유실 방지 — flush 중 서버가 영구 거부(4xx)해 큐에서 드롭된 세트 알림.
// 버퍼는 client.ts 모듈 전역이라 어느 화면에서든 같은 내용을 보여준다.
// Log·세션 상세(/history/{id}·/history/new) 공용.
export default function FlushFailuresBanner({ exercises }: { exercises: Exercise[] }) {
  const [failures, setFailures] = useState<FlushFailure[]>([]);
  useEffect(() => subscribeFlushFailures(setFailures), []);
  if (failures.length === 0) return null;
  const exName = (id: number) => exercises.find((e) => e.id === id)?.name_ko ?? `종목 ${id}`;
  return (
    <Card className="border border-danger/50">
      <p className="text-sm font-semibold text-danger">
        전송이 거부되어 저장되지 않은 세트가 있습니다
      </p>
      <ul className="mt-1 flex flex-col gap-0.5 text-xs text-muted">
        {failures.map((f) => (
          <li key={f.item.client_id}>
            {f.item.date} · {exName(f.item.exercise_id)} {fmtWeight(f.item.weight_kg)}kg×
            {f.item.reps} — {f.detail}
          </li>
        ))}
      </ul>
      <Button variant="ghost" className="mt-2" onClick={dismissFlushFailures}>
        확인
      </Button>
    </Card>
  );
}
