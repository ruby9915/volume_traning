// §3.7A 소급 적용 확인 다이얼로그 — 설정 "물어보기"일 때만 열린다.
// "다시 묻지 않기" 체크 후 적용/적용 안 함을 고르면 호출측(useIntentBackfill)이 그 선택을
// 설정 기본값으로 저장한다. 배경 탭 닫기(onClose)는 이번 1회 취소 — 설정 미저장.
import { useEffect, useState } from "react";
import type { MuscleCode } from "../../api/types";
import { MUSCLE_NAME_KO } from "../../api/types";
import Button from "../Button";
import Modal from "../Modal";

export default function IntentBackfillModal({
  open,
  count,
  code,
  busy = false,
  onResolve,
  onClose,
}: {
  open: boolean;
  /** 소급 대상 세트 수 (저장된 세트 + 전송 대기 세트) */
  count: number;
  /** 바꿀 의도 (null = 기본) */
  code: MuscleCode | null;
  busy?: boolean;
  onResolve: (apply: boolean, remember: boolean) => void;
  onClose: () => void;
}) {
  const [remember, setRemember] = useState(false);
  useEffect(() => {
    if (open) setRemember(false); // 열릴 때마다 체크 해제 — 이전 선택이 새 다이얼로그에 남지 않게
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!busy) onClose();
      }}
      title="기존 세트에도 적용할까요?"
    >
      <p className="text-sm text-muted">
        이미 저장된 이 종목 {count}세트의 의도를{" "}
        <span className="font-semibold text-text">
          {code != null ? MUSCLE_NAME_KO[code] : "기본"}
        </span>
        (으)로 변경합니다.
      </p>
      <label className="mt-3 flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          className="h-5 w-5 accent-accent"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
        />
        다시 묻지 않기 (설정에 저장)
      </label>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Button variant="secondary" disabled={busy} onClick={() => onResolve(false, remember)}>
          적용 안 함
        </Button>
        <Button disabled={busy} onClick={() => onResolve(true, remember)}>
          적용
        </Button>
      </div>
    </Modal>
  );
}
