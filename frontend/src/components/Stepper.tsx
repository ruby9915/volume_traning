import { useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";

/** 길게 누르기 반복 증가 (README Interactions: "길게 누르면 반복 증가") */
const HOLD_DELAY_MS = 450;
const HOLD_REPEAT_MS = 120;

export interface StepperProps {
  label: string;
  value: number;
  step: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  inputMode?: "decimal" | "numeric"; // 숫자 직접 탭 시 키패드 종류
  suffix?: string;
  /** 웰 컨테이너에 추가 (Log에서 flex-[1.4] 등 폭 배분용) */
  className?: string;
}

/**
 * 시안: 웰(bg-well, radius-well) 안에 라벨 + [− 값 ＋].
 * 값 = 숫자폰트(다크 Oswald 44px 600 / 라이트 Space Grotesk 36px 700, --text-stepper).
 * ± 버튼 = 다크: 배경 없음 accent 텍스트 28px / 라이트: 흰 카드 버튼 radius 12px + 그림자.
 * 히트타깃 44px+ 유지. 값 직접 탭 → 키패드 입력(기존 동작).
 */
export default function Stepper({
  label,
  value,
  step,
  onChange,
  min = 0,
  max = 999,
  inputMode = "decimal",
  suffix,
  className = "",
}: StepperProps) {
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const clamp = (n: number) => Math.min(max, Math.max(min, Math.round(n * 100) / 100));

  const commit = () => {
    const n = parseFloat(inputRef.current?.value ?? "");
    if (!Number.isNaN(n)) onChange(clamp(n));
    setEditing(false);
  };

  // 길게 누르기: 항상 최신 value/step/onChange를 쓰도록 ref 경유 (interval 클로저 stale 방지)
  const stepFnRef = useRef<(dir: 1 | -1) => void>(() => {});
  stepFnRef.current = (dir) => onChange(clamp(value + dir * step));
  const holdRef = useRef<{ timeout: number; interval: number; fired: boolean } | null>(null);

  const stopHold = () => {
    const h = holdRef.current;
    if (!h) return;
    window.clearTimeout(h.timeout);
    window.clearInterval(h.interval);
    // fired 플래그는 뒤따르는 click 이벤트가 판정해야 하므로 여기서 지우지 않는다
  };

  const startHold = (dir: 1 | -1) => {
    stopHold();
    const timeout = window.setTimeout(() => {
      const h = holdRef.current;
      if (!h) return;
      h.fired = true;
      stepFnRef.current(dir);
      h.interval = window.setInterval(() => stepFnRef.current(dir), HOLD_REPEAT_MS);
    }, HOLD_DELAY_MS);
    holdRef.current = { timeout, interval: 0, fired: false };
  };

  useEffect(() => stopHold, []);

  /** 반복이 발동했으면 pointerup 후의 click 1회를 무시, 아니면 단발 스텝 (키보드 Enter도 이 경로) */
  const pmHandlers = (dir: 1 | -1) => ({
    onPointerDown: () => startHold(dir),
    onPointerUp: stopHold,
    onPointerLeave: stopHold,
    onPointerCancel: stopHold,
    onContextMenu: (e: ReactMouseEvent) => e.preventDefault(),
    onClick: () => {
      const h = holdRef.current;
      if (h?.fired) {
        h.fired = false;
        return;
      }
      stepFnRef.current(dir);
    },
  });

  const pmButton =
    "touch-target flex h-11 w-11 select-none items-center justify-center text-2xl leading-none " +
    "rounded-[12px] bg-surface text-text shadow-card active:brightness-[0.95] " +
    "dark:h-12 dark:rounded-none dark:bg-transparent dark:text-[28px] dark:text-accent dark:shadow-none dark:active:brightness-125";

  return (
    <div
      className={`flex flex-col items-center gap-1 rounded-well bg-well p-2.5 ${className}`}
    >
      {/* 라벨: 라이트 시안은 "중량 kg" 소문자·기본 자간, 다크만 "KG/REPS" 대문자+wide tracking */}
      <span className="text-[10px] font-semibold text-muted dark:tracking-widest dark:uppercase">
        {label}
      </span>
      <div className="flex w-full items-center justify-center gap-1">
        <button type="button" aria-label={`${label} 감소`} className={pmButton} {...pmHandlers(-1)}>
          −
        </button>
        {editing ? (
          <input
            ref={inputRef}
            type="text"
            inputMode={inputMode}
            defaultValue={String(value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
            }}
            className="min-w-0 flex-1 rounded-row border border-accent bg-surface text-center font-numeric text-stepper font-bold text-text focus:outline-none dark:font-semibold"
          />
        ) : (
          <button
            type="button"
            className="touch-target min-w-0 flex-1 text-center font-numeric text-stepper font-bold text-text dark:font-semibold"
            onClick={() => setEditing(true)}
          >
            {value}
            {suffix ? <span className="text-xs font-normal text-muted"> {suffix}</span> : null}
          </button>
        )}
        <button type="button" aria-label={`${label} 증가`} className={pmButton} {...pmHandlers(1)}>
          +
        </button>
      </div>
    </div>
  );
}
