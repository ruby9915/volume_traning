import type { ButtonHTMLAttributes } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "md" | "lg";
  full?: boolean;
}

/**
 * 시안 매핑:
 * - primary: accent 필 + on-accent 텍스트 (다크=bg색 텍스트 / 라이트=흰 텍스트+에메랄드 그림자),
 *   radius·그림자는 테마 토큰이 결정. 탭 시 살짝 스케일다운(README Interactions).
 * - secondary: surface-2 + 헤어라인 보더 (헤더 '완료' 버튼류)
 * - ghost / danger: 기존 역할 유지, 토큰만 교체
 */
const VARIANTS = {
  primary:
    "bg-accent font-extrabold text-on-accent shadow-btn transition-transform duration-100 " +
    "hover:brightness-[1.08] active:scale-[0.98] active:bg-accent-deep",
  secondary: "border border-line bg-surface-2 font-semibold text-text active:bg-line",
  ghost: "bg-transparent text-muted active:bg-surface-2",
  danger: "border border-danger/40 bg-danger/15 text-danger active:bg-danger/25",
} as const;

const SIZES = {
  md: "min-h-12 px-4 text-base",
  // 주 액션(세트 완료 등): 라이트 56px/16px, 다크 58px/17px (README L50)
  lg: "min-h-14 px-5 text-base dark:min-h-[58px] dark:text-[17px]",
} as const;

export default function Button({
  variant = "primary",
  size = "md",
  full = false,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`touch-target rounded-btn disabled:opacity-40 ${VARIANTS[variant]} ${SIZES[size]} ${full ? "w-full" : ""} ${className}`}
      {...rest}
    />
  );
}
