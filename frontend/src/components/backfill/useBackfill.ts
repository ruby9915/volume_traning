// 소급 적용 흐름 (§10.2 타겟 · §15.3 머신) — 기록(Log)·세션 상세(SessionDetail) 공용 훅.
//
// 종목 카드의 칩(타겟·머신)을 바꿨을 때 이미 저장된 같은 종목 세트를 어떻게 할지는
// 설정(targetBackfill — 타겟·머신 공용)이 정한다:
//   물어보기(기본) → 확인 다이얼로그(prompt) / 항상 적용 → 즉시 run / 적용 안 함 → 아무것도 안 함.
// 다이얼로그에서 "다시 묻지 않기"를 켜고 고르면 그 선택이 설정 기본값으로 저장된다.
// 배경 탭 닫기(dismiss)는 이번 1회 취소 — 설정은 저장하지 않는다.
import { useState } from "react";
import type { MachineRef, TargetCode } from "../../api/types";
import { useAppStore } from "../../store";

/** 소급 적용 대상 — ids = 저장된 세트(PATCH), clientIds = 전송 대기(outbox) 세트(큐 직접 갱신) */
export type CardBackfill = { ids: number[]; clientIds: string[] } & (
  | { kind: "target"; code: TargetCode }
  | { kind: "machine"; machine: MachineRef | null }
);

export function useBackfill(run: (target: CardBackfill) => Promise<void>) {
  const mode = useAppStore((s) => s.targetBackfill);
  const setMode = useAppStore((s) => s.setTargetBackfill);
  const [prompt, setPrompt] = useState<CardBackfill | null>(null);

  /** 소급 대상이 있을 때 호출 — 설정에 따라 즉시 실행하거나 다이얼로그를 연다 */
  const request = async (target: CardBackfill): Promise<void> => {
    if (target.ids.length === 0 && target.clientIds.length === 0) return;
    if (mode === "never") return;
    if (mode === "always") {
      await run(target);
      return;
    }
    setPrompt(target);
  };

  /** 다이얼로그 확정 (적용 / 적용 안 함) */
  const resolve = async (apply: boolean, remember: boolean): Promise<void> => {
    const target = prompt;
    setPrompt(null);
    if (target == null) return;
    if (remember) setMode(apply ? "always" : "never");
    if (apply) await run(target);
  };

  const dismiss = () => setPrompt(null);

  return { prompt, request, resolve, dismiss };
}
