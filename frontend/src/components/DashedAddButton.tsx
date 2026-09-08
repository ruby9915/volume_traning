import type { ReactNode } from "react";

/** 대시드 보더 전폭 추가 버튼 — "＋ 종목 추가"·"＋ 세트 추가" (README: 종목 추가 버튼 패턴) */
export default function DashedAddButton({
  onClick,
  children,
  className = "",
}: {
  onClick: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-12 w-full items-center justify-center rounded-sub border-[1.5px] border-dashed border-line-dashed text-sm font-medium text-muted active:bg-surface-2 ${className}`}
    >
      {children}
    </button>
  );
}
