// §10.2 타겟 분류 — 서버(GET /api/targets)가 정본. 앱 세션 동안 한 번만 받아 캐시한다.
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTargets } from "../api/client";
import type { Region, Target, TargetCode } from "../api/types";
import { REGION_NAMES_KO } from "../api/types";

export interface TargetIndex {
  targets: Target[];
  byCode: Map<TargetCode, Target>;
  /** 근육(level 2) 목록, 서버 정렬 순 */
  muscles: Target[];
  /** 근육 코드 → 세부(level 3) 목록 */
  childrenOf: (code: TargetCode) => Target[];
  /** 코드 → 한글 이름 (모르는 코드는 코드 그대로) */
  nameOf: (code: TargetCode | null | undefined) => string;
  /** 코드 → 근육(level 2) 코드 (세부면 부모, 근육이면 자기) */
  muscleOf: (code: TargetCode) => TargetCode;
  regionOf: (code: TargetCode) => Region | null;
  regionNameOf: (code: TargetCode) => string;
}

const EMPTY: Target[] = [];

export function useTargets(): TargetIndex & { isLoading: boolean } {
  const q = useQuery({ queryKey: ["targets"], queryFn: fetchTargets, staleTime: Infinity });
  const targets = q.data ?? EMPTY;
  const index = useMemo<TargetIndex>(() => {
    const byCode = new Map(targets.map((t) => [t.code, t]));
    const children = new Map<TargetCode, Target[]>();
    for (const t of targets) {
      if (t.parent_code) {
        const list = children.get(t.parent_code) ?? [];
        list.push(t);
        children.set(t.parent_code, list);
      }
    }
    return {
      targets,
      byCode,
      muscles: targets.filter((t) => t.level === 2),
      childrenOf: (code) => children.get(code) ?? EMPTY,
      nameOf: (code) => (code ? (byCode.get(code)?.name_ko ?? code) : ""),
      muscleOf: (code) => byCode.get(code)?.parent_code ?? code,
      regionOf: (code) => byCode.get(code)?.region ?? null,
      regionNameOf: (code) => {
        const r = byCode.get(code)?.region;
        return r ? REGION_NAMES_KO[r] : "";
      },
    };
  }, [targets]);
  return { ...index, isLoading: q.isLoading };
}
