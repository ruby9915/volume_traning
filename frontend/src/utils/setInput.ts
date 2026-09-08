// §3.3 세트 입력 검증 — weight 0~500 + 0.25kg 배수, reps 1~100 정수.
// 서버(schemas.Weight/Reps → 422)와 같은 규칙을 저장 전에 클라이언트에서 먼저 잡는다.
// 기록(Log)·세션 상세(SessionDetail) 공용 — 문구도 한 곳에서 관리한다.

export function validateSetInput(weightKg: number, reps: number): string | null {
  if (weightKg < 0 || weightKg > 500) return "중량은 0~500kg 범위로 입력하세요";
  if (Math.abs(weightKg * 4 - Math.round(weightKg * 4)) > 1e-9) {
    return "중량은 0.25kg 단위로 입력하세요";
  }
  if (!Number.isInteger(reps) || reps < 1 || reps > 100) {
    return "횟수는 1~100 사이 정수로 입력하세요";
  }
  return null;
}
