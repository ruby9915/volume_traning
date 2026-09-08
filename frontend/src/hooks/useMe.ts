// 로그인한 사용자 (GET /api/auth/me). 관리자 탭 노출·설정 화면 계정 표시용.
import { useQuery } from "@tanstack/react-query";
import { fetchMe, getToken } from "../api/client";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: getToken() != null,
    staleTime: 5 * 60_000,
  });
}
