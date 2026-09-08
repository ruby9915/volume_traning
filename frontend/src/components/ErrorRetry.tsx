import Button from "./Button";

/** 조회 실패 안내 + 재시도 — 분석 카드·이력 목록 공용 */
export default function ErrorRetry({
  onRetry,
  message = "불러오지 못했습니다",
  className = "py-6",
}: {
  onRetry: () => void;
  message?: string;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      <p className="text-sm text-muted">{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        다시 시도
      </Button>
    </div>
  );
}
