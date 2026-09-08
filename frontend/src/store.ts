import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { TargetCode } from "./api/types";
import { todayStr } from "./utils/date";

export type WeightStep = 1.25 | 2.5 | 5;
export type RestTarget = 60 | 90 | 120 | 180 | 240;

/** 휴식 타이머 목표시간 선택지 (Settings UI·Log 진행바 공용) */
export const REST_TARGET_OPTIONS: RestTarget[] = [60, 90, 120, 180, 240];

// §10.2 소급 적용 확인의 설정화 — 타겟 변경 시 이미 저장된 같은 종목 세트 처리
export type TargetBackfillMode = "ask" | "always" | "never";
export const TARGET_BACKFILL_OPTIONS: TargetBackfillMode[] = ["ask", "always", "never"];

export interface StepperInput {
  weight_kg: number;
  reps: number;
  is_warmup: boolean;
}

// 프리필 3순위는 "빈 값" (§5.3) — 임의 기본 중량 금지, 0에서 시작
const DEFAULT_STEPPER: StepperInput = { weight_kg: 0, reps: 8, is_warmup: false };

interface AppState {
  activeExerciseId: number | null;
  stepper: StepperInput;
  restStartedAt: number | null; // epoch ms — 휴식 카운트업 시작시각
  // §10.2 세트 타겟 — 종목 카드 단위 sticky (값 없음 = 종목 기본 타겟).
  // persist 제외 + endSession에서 초기화 → 세션 간 carry-over 없음
  targets: Partial<Record<number, TargetCode>>;
  // targets가 설정된 날짜(todayStr, 03:00 경계). 앱을 켠 채 날짜가 바뀌면
  // 새 lazy 세션이 생기므로 stale targets를 폐기하기 위한 스탬프
  targetsDate: string | null;
  weightStep: WeightStep; // 설정: 중량 증분 (persist)
  restTargetSeconds: RestTarget; // 설정: 휴식 목표시간 (persist) — Log 진행바의 분모
  // 설정: 타겟 변경 시 기존 세트 — 물어보기(기본)/항상 적용/적용 안 함 (persist)
  targetBackfill: TargetBackfillMode;
  setActiveExercise: (id: number | null) => void;
  setStepper: (patch: Partial<StepperInput>) => void;
  setTarget: (exerciseId: number, code: TargetCode | null) => void;
  clearTargets: () => void; // 03:00 경계 통과 등 — targets만 초기화
  startRest: (at?: number) => void;
  clearRest: () => void;
  setWeightStep: (step: WeightStep) => void;
  setRestTarget: (seconds: RestTarget) => void;
  setTargetBackfill: (mode: TargetBackfillMode) => void;
  endSession: () => void; // '세션 완료' — 클라이언트 활성 상태 초기화 (서버 상태 아님, §5.3)
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeExerciseId: null,
      stepper: DEFAULT_STEPPER,
      restStartedAt: null,
      targets: {},
      targetsDate: null,
      weightStep: 2.5,
      restTargetSeconds: 120,
      targetBackfill: "ask",
      setActiveExercise: (id) => set({ activeExerciseId: id }),
      setStepper: (patch) => set((s) => ({ stepper: { ...s.stepper, ...patch } })),
      setTarget: (exerciseId, code) =>
        set((s) => {
          const next = { ...s.targets };
          if (code == null) delete next[exerciseId];
          else next[exerciseId] = code;
          return { targets: next, targetsDate: todayStr() };
        }),
      clearTargets: () => set({ targets: {}, targetsDate: null }),
      startRest: (at = Date.now()) => set({ restStartedAt: at }),
      clearRest: () => set({ restStartedAt: null }),
      setWeightStep: (step) => set({ weightStep: step }),
      setRestTarget: (seconds) => set({ restTargetSeconds: seconds }),
      setTargetBackfill: (mode) => set({ targetBackfill: mode }),
      endSession: () =>
        set({
          activeExerciseId: null,
          stepper: DEFAULT_STEPPER,
          restStartedAt: null,
          targets: {},
          targetsDate: null,
        }),
    }),
    {
      name: "vt_settings",
      version: 2,
      // v1 저장값의 intentBackfill → targetBackfill (같은 3택)
      migrate: (persisted) => {
        const s = (persisted ?? {}) as Record<string, unknown>;
        return {
          ...s,
          targetBackfill: (s.targetBackfill ?? s.intentBackfill ?? "ask") as TargetBackfillMode,
        };
      },
      partialize: (s) => ({
        weightStep: s.weightStep,
        restTargetSeconds: s.restTargetSeconds,
        targetBackfill: s.targetBackfill,
      }),
    },
  ),
);
