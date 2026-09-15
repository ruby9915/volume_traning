// §13 아바타 — 이모지(avatar 문자열)가 있으면 그것, 없으면 표시 이름 이니셜. 파일 업로드 없음.
const SIZES = { sm: "h-9 w-9 text-base", md: "h-14 w-14 text-2xl", lg: "h-20 w-20 text-4xl" } as const;

export function initialsOf(name: string): string {
  const t = name.trim();
  if (!t) return "?";
  // 한글은 첫 글자, 영문은 단어 첫 글자 두 개
  if (/[가-힣]/.test(t[0])) return t[0];
  return t
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export default function Avatar({
  avatar,
  name,
  size = "md",
}: {
  avatar: string | null;
  name: string;
  size?: keyof typeof SIZES;
}) {
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full bg-accent-glow font-bold text-accent ${SIZES[size]}`}
    >
      {avatar || initialsOf(name)}
    </span>
  );
}
