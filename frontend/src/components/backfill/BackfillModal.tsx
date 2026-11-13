// 소급 적용 확인 다이얼로그 (§10.2 타겟 · §15.3 머신) — 설정 "물어보기"일 때만 열린다.
// "다시 묻지 않기" 체크 후 적용/적용 안 함을 고르면 호출측(useBackfill)이 그 선택을
// 설정 기본값으로 저장한다. 배경 탭 닫기(onClose)는 이번 1회 취소 — 설정 미저장.
import { useEffect, useState } from "react";
import { useTargets } from "../../hooks/useTargets";
import Button from "../Button";
import Modal from "../Modal";
import type { CardBackfill } from "./useBackfill";

export default function BackfillModal({
  prompt,
  busy = false,
  onResolve,
  onClose,
}: {
  /** 소급 대상 — null이면 닫힘 */
  prompt: CardBackfill | null;
  busy?: boolean;
  onResolve: (apply: boolean, remember: boolean) => void;
  onClose: () => void;
}) {
  const { nameOf } = useTargets();
  const [remember, setRemember] = useState(false);
  const open = prompt != null;
  useEffect(() => {
    if (open) setRemember(false);
  }, [open]);

  const count = (prompt?.ids.length ?? 0) + (prompt?.clientIds.length ?? 0);
  const strong = (text: string) => <span className="font-semibold text-text">{text}</span>;

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!busy) onClose();
      }}
      title="기존 세트에도 적용할까요?"
    >
      <p className="text-sm text-muted">
        이미 저장된 이 종목 {count}세트의{" "}
        {prompt?.kind === "machine" ? (
          prompt.machine ? (
            <>머신을 {strong(prompt.machine.name_ko)}(으)로 변경합니다.</>
          ) : (
            <>머신을 {strong("머신 없음")}으로 변경합니다.</>
          )
        ) : (
          <>타겟을 {strong(nameOf(prompt?.code))}(으)로 변경합니다.</>
        )}
      </p>
      <label className="mt-3 flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          className="h-5 w-5 accent-accent"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
        />
        다시 묻지 않기 (설정에 저장 · 타겟·머신 공용)
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
