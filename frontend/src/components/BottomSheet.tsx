import { useEffect, useState, type ReactNode } from "react";

export interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

// iOS Safari는 키보드가 떠도 레이아웃 뷰포트를 줄이지 않아(visual viewport만 축소)
// bottom-0 고정 시트가 키보드 뒤로 가려진다. visualViewport 기준으로
// "레이아웃 뷰포트 하단 ~ 키보드 상단" 간격(inset)을 계산해 시트를 그만큼 올린다.
// visualViewport 미지원 브라우저는 inset 0 → 기존 동작 그대로.
function useKeyboardInset(active: boolean): number {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    if (!active) {
      setInset(0);
      return;
    }
    const vv = window.visualViewport;
    if (!vv) return;

    const update = () => {
      const next = window.innerHeight - vv.height - vv.offsetTop;
      // 키보드 없을 때의 소수점 오차·미세 변동은 0으로 처리
      setInset(next > 1 ? Math.round(next) : 0);
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      setInset(0);
    };
  }, [active]);

  return inset;
}

export default function BottomSheet({ open, onClose, title, children }: BottomSheetProps) {
  const keyboardInset = useKeyboardInset(open);

  if (!open) return null;

  // inset>0(키보드 표시)일 때만 인라인 스타일 적용 — 평소엔 클래스(max-h-[85dvh]) 그대로.
  const sheetStyle =
    keyboardInset > 0
      ? {
          transform: `translateY(-${keyboardInset}px)`,
          maxHeight: `min(85dvh, calc(100dvh - ${keyboardInset}px))`,
        }
      : undefined;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50 dark:bg-black/60" onClick={onClose} />
      <div
        className="absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-card-lg border-t border-hairline bg-surface p-4 shadow-modal safe-bottom"
        style={sheetStyle}
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />
        <div className="mb-2 flex items-center justify-between">
          {title ? <h2 className="text-lg font-bold">{title}</h2> : <span />}
          <button type="button" aria-label="닫기" className="touch-target text-muted" onClick={onClose}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
