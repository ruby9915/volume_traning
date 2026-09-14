// §10.4 머신 검색 시트 — 아카이브 전체를 내려받지 않고 서버 검색(q·brand·limit)으로 고른다.
// 브랜드 칩 → 검색어 → 결과 탭 = onPick. 없으면 "직접 추가"로 아카이브에 새 머신을 만든다(공용).
// 시트는 선택 후 자동으로 닫히지 않는다 — 호출측이 onPick에서 닫는다.
import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiErrorMessage, createMachine, fetchMachineBrands, fetchMachines } from "../../api/client";
import type { Machine } from "../../api/types";
import { useTargets } from "../../hooks/useTargets";
import BottomSheet from "../BottomSheet";
import Button from "../Button";
import Spinner from "../Spinner";

const LIMIT = 60;
const FIELD_CLS =
  "min-h-12 w-full rounded-xl border border-line bg-bg px-4 placeholder:text-faint focus:border-accent focus:outline-none";

function CustomMachineForm({ onCreated, onCancel }: { onCreated: (m: Machine) => void; onCancel: () => void }) {
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [nameKo, setNameKo] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!brand.trim() || !model.trim()) {
      setErr("브랜드와 모델명을 입력하세요");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const m = await createMachine({
        brand: brand.trim(),
        model: model.trim(),
        ...(nameKo.trim() ? { name_ko: nameKo.trim() } : {}),
      });
      onCreated(m);
    } catch (e) {
      setErr(apiErrorMessage(e, "추가하지 못했습니다"));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-semibold">머신 직접 추가</p>
      <p className="text-xs text-muted">아카이브에 없는 머신만 추가하세요. 추가한 머신은 모두에게 검색됩니다.</p>
      <input value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="브랜드 (예: 뉴텍)" maxLength={50} className={FIELD_CLS} />
      <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="모델명 (제조사 표기)" maxLength={50} className={FIELD_CLS} />
      <input value={nameKo} onChange={(e) => setNameKo(e.target.value)} placeholder="한글 별칭 (선택)" maxLength={50} className={FIELD_CLS} />
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      <div className="flex gap-2">
        <Button variant="ghost" onClick={onCancel} disabled={busy}>취소</Button>
        <Button full onClick={() => void submit()} disabled={busy}>{busy ? <Spinner size="sm" /> : "추가하고 선택"}</Button>
      </div>
    </div>
  );
}

export default function MachinePicker({
  open,
  onClose,
  onPick,
  title = "머신 검색",
}: {
  open: boolean;
  onClose: () => void;
  onPick: (m: Machine) => void;
  title?: string;
}) {
  const { nameOf } = useTargets();
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  const [brand, setBrand] = useState("");
  const [custom, setCustom] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDq(q.trim()), 150);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    if (!open) setCustom(false);
  }, [open]);

  const brandsQ = useQuery({ queryKey: ["machine-brands"], queryFn: fetchMachineBrands, staleTime: 5 * 60_000 });
  const active = dq.length > 0 || brand !== "";
  const resultsQ = useQuery({
    queryKey: ["machines", "search", dq, brand],
    queryFn: () => fetchMachines({ q: dq, brand, limit: LIMIT }),
    enabled: open && active,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
  const results = resultsQ.data ?? [];

  return (
    <BottomSheet open={open} onClose={onClose} title={title}>
      {custom ? (
        <CustomMachineForm onCreated={onPick} onCancel={() => setCustom(false)} />
      ) : (
        <div className="flex flex-col gap-3">
          <input
            id="machine-search"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="모델명·한글 별칭 검색 (예: 핵 스쿼트, incline)"
            className={FIELD_CLS}
          />
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setBrand("")}
              className={`rounded-chip border px-2.5 py-1 text-xs ${brand === "" ? "border-accent/40 bg-accent-glow font-semibold text-accent" : "border-line text-muted"}`}
            >
              전체
            </button>
            {(brandsQ.data ?? []).map((b) => (
              <button
                key={b.brand}
                type="button"
                onClick={() => setBrand(brand === b.brand ? "" : b.brand)}
                className={`rounded-chip border px-2.5 py-1 text-xs ${brand === b.brand ? "border-accent/40 bg-accent-glow font-semibold text-accent" : "border-line text-muted"}`}
              >
                {b.brand} <span className="font-numeric text-[10px] text-faint">{b.count}</span>
              </button>
            ))}
          </div>
          <div className="min-h-[40dvh]">
            {!active ? (
              <p className="px-1 py-3 text-sm text-muted">
                브랜드를 고르거나 검색어를 입력하세요. 고른 머신은 내 머신에 담겨 다음부터 바로 보입니다.
              </p>
            ) : resultsQ.isLoading ? (
              <div className="flex justify-center py-6"><Spinner /></div>
            ) : resultsQ.isError ? (
              <p className="px-1 py-3 text-sm text-danger">{apiErrorMessage(resultsQ.error, "검색하지 못했습니다")}</p>
            ) : results.length === 0 ? (
              <p className="px-1 py-3 text-sm text-muted">검색 결과가 없습니다.</p>
            ) : (
              <ul className="divide-y divide-line">
                {results.map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => onPick(m)}
                      className="flex w-full items-center justify-between gap-3 py-2.5 text-left active:bg-surface-2"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{m.name_ko}</span>
                        <span className="block truncate text-xs text-muted">{m.brand} · {m.model}</span>
                      </span>
                      {m.target ? (
                        <span className="shrink-0 rounded-chip border border-line px-2 py-0.5 text-[11px] text-muted">{nameOf(m.target)}</span>
                      ) : null}
                    </button>
                  </li>
                ))}
                {results.length >= LIMIT ? (
                  <li className="py-2 text-center text-xs text-faint">상위 {LIMIT}개만 표시 — 검색어를 더 구체적으로</li>
                ) : null}
              </ul>
            )}
          </div>
          <Button variant="secondary" full onClick={() => setCustom(true)}>
            ＋ 아카이브에 없으면 직접 추가
          </Button>
        </div>
      )}
    </BottomSheet>
  );
}
