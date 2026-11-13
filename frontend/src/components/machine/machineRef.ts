// §15 세트·카드의 머신 값 다루기 — 기록(Log)·세션 상세(SessionDetail) 공용.
import type { MachineRef } from "../../api/types";

/** 서버 응답의 (machine_id, machine_name) 쌍 → MachineRef. id가 없으면 null(머신 없음) */
export function machineRefOf(
  id: number | null | undefined,
  name: string | null | undefined,
): MachineRef | null {
  return id != null ? { id, name_ko: name ?? "머신" } : null;
}

export function sameMachine(a: MachineRef | null, b: MachineRef | null): boolean {
  return (a?.id ?? null) === (b?.id ?? null);
}

/** 세트 행의 머신 뱃지 문구 — 카드의 머신과 다른 세트에만 붙인다 */
export function machineBadgeLabel(name: string | null): string {
  return name ?? "머신 없음";
}
