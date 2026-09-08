export interface SpinnerProps {
  size?: "sm" | "md";
  className?: string;
}

export default function Spinner({ size = "md", className = "" }: SpinnerProps) {
  const dim = size === "sm" ? "h-4 w-4 border-2" : "h-8 w-8 border-[3px]";
  return (
    <div
      aria-label="로딩 중"
      className={`animate-spin rounded-full border-line border-t-accent ${dim} ${className}`}
    />
  );
}
