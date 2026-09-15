// 카드·섹션 접힘 상태 — 기기별로 기억 (localStorage, 실패해도 기본값으로 동작).
// 분석 탭 "최근 PR" 카드, 종목 관리 즐겨찾기 등 접기/펼치기가 있는 곳의 공용 훅 (2026-09-15).
import { useState } from "react";

export function useCollapsed(key: string, initial = false): [boolean, () => void] {
  const storageKey = `vt_collapsed_${key}`;
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      const v = localStorage.getItem(storageKey);
      return v === null ? initial : v === "1";
    } catch {
      return initial;
    }
  });
  const toggle = () =>
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(storageKey, next ? "1" : "0");
      } catch {
        /* 저장 실패는 무시 — 이번 세션만 유지 */
      }
      return next;
    });
  return [collapsed, toggle];
}

/** 접기/펼치기 버튼 라벨 — 화면마다 같은 문구를 쓴다 */
export function collapseLabel(collapsed: boolean): string {
  return collapsed ? "펼치기 ▾" : "접기 ▴";
}
