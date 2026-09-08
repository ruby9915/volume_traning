import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { MuscleCode } from "./api/types";
import { todayStr } from "./utils/date";

export type WeightStep = 1.25 | 2.5 | 5;
export type RestTarget = 60 | 90 | 120 | 180 | 240;

/** 휴식 타이머 목표시간 선택지 (Settings UI·Log 진행바 공용) */
export const REST_TARGET_OPTIONS: RestTarget[] = [60, 90, 120, 180, 240];

// §3.7A 소급 적용 확인의 설정화 — 의도 변경 시 이미 저장된 같은 종목 세트 처리
export type IntentBackfillMode = "ask" | "always" | "never";
export const INTENT_BACKFILL_OPTIONS: IntentBackfillMode[] = ["ask", "always", "never"];

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
  // §3.7A 기록 의도 주동근 — 종목 카드 단위 sticky. persist 제외 + endSession에서 초기화
  // → 세션 간 carry-over 없음 (새 세션·앱 재시작은 항상 "기본")
  intents: Partial<Record<number, MuscleCode>>;
  // intents가 설정된 날짜(todayStr, 03:00 경계). 앱을 켠 채 날짜가 바뀌면
  // 새 lazy 세션이 생기므로 stale intents를 폐기하기 위한 스탬프 (§3.7A carry-over 금지)
  intentsDate: string | null;
  weightStep: WeightStep; // 설정: 중량 증분 (persist)
  restTargetSeconds: RestTarget; // 설정: 휴식 목표시간 (persist) — Log 진행바의 분모
  // 설정: 의도 변경 시 기존 세트 — 물어보기(기본)/항상 적용/적용 안 함 (persist, §3.7A)
  intentBackfill: IntentBackfillMode;
  setActiveExercise: (id: number | null) => void;
  setStepper: (patch: Partial<StepperInput>) => void;
  setIntent: (exerciseId: number, code: MuscleCode | null) => void;
  clearIntents: () => void; // 03:00 경계 통과 등 — intents만 초기화
  startRest: (at?: number) => void;
  clearRest: () => void;
  setWeightStep: (step: WeightStep) => void;
  setRestTarget: (seconds: RestTarget) => void;
  setIntentBackfill: (mode: IntentBackfillMode) => void;
  endSession: () => void; // '세션 완료' — 클라이언트 활성 상태 초기화 (서버 상태 아님, §5.3)
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeExerciseId: null,
      stepper: DEFAULT_STEPPER,
      restStartedAt: null,
      intents: {},
      intentsDate: null,
      weightStep: 2.5,
      restTargetSeconds: 120,
      intentBackfill: "ask",
      setActiveExercise: (id) => set({ activeExerciseId: id }),
      setStepper: (patch) => set((s) => ({ stepper: { ...s.stepper, ...patch } })),
      setIntent: (exerciseId, code) =>
        set((s) => {
          const next = { ...s.intents };
          if (code == null) delete next[exerciseId];
          else next[exerciseId] = code;
          return { intents: next, intentsDate: todayStr() };
        }),
      clearIntents: () => set({ intents: {}, intentsDate: null }),
      startRest: (at = Date.now()) => set({ restStartedAt: at }),
      clearRest: () => set({ restStartedAt: null }),
      setWeightStep: (step) => set({ weightStep: step }),
      setRestTarget: (seconds) => set({ restTargetSeconds: seconds }),
      setIntentBackfill: (mode) => set({ intentBackfill: mode }),
      endSession: () =>
        set({
          activeExerciseId: null,
          stepper: DEFAULT_STEPPER,
          restStartedAt: null,
          intents: {},
          intentsDate: null,
        }),
    }),
    {
      name: "vt_settings",
      partialize: (s) => ({
        weightStep: s.weightStep,
        restTargetSeconds: s.restTargetSeconds,
        intentBackfill: s.intentBackfill,
      }),
    },
  ),
);
