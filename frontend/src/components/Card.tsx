import type { ReactNode } from "react";

export interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  /**
   * 시안 카드 위계:
   * - default: 일반 카드 (surface + radius-card + shadow-card; 다크는 보더·그림자 없음)
   * - sunken: 완료 종목 카드·리스트 행 (다크 #12100e / 라이트 흰 카드)
   * - live: 진행중 종목 카드 (다크 accent 글로우 링 / 라이트 에메랄드 소프트 섀도)
   * - hero: 분석 히어로 (라이트 = 잉크 다크카드, 다크 = surface)
   */
  variant?: "default" | "sunken" | "live" | "hero";
}

const VARIANTS = {
  default: "bg-surface rounded-card shadow-card",
  sunken: "bg-surface-sunken rounded-sub shadow-card",
  live: "bg-surface rounded-card-lg shadow-live",
  hero: "bg-hero text-hero-text rounded-card-lg shadow-card",
} as const;

export default function Card({
  children,
  className = "",
  onClick,
  variant = "default",
}: CardProps) {
  return (
    <div
      onClick={onClick}
      className={`p-4 ${VARIANTS[variant]} ${onClick ? "cursor-pointer active:brightness-[0.97] dark:active:brightness-110" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
