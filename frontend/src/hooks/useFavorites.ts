// §10.3 즐겨찾기 — 종목 선택 시트·종목 관리 화면 공용. 순서 있는 id 목록.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addFavorite, fetchFavorites, removeFavorite, replaceFavorites } from "../api/client";
import type { Favorites } from "../api/types";

const KEY = ["favorites"];

export function useFavorites() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: fetchFavorites, staleTime: 60_000 });
  const ids = q.data?.exercise_ids ?? [];
  const idSet = new Set(ids);

  const apply = (data: Favorites) => qc.setQueryData(KEY, data);
  const add = useMutation({ mutationFn: addFavorite, onSuccess: apply });
  const remove = useMutation({ mutationFn: removeFavorite, onSuccess: apply });
  const replace = useMutation({ mutationFn: replaceFavorites, onSuccess: apply });

  return {
    ids,
    isFavorite: (exerciseId: number) => idSet.has(exerciseId),
    toggle: (exerciseId: number) => {
      if (idSet.has(exerciseId)) remove.mutate(exerciseId);
      else add.mutate(exerciseId);
    },
    reorder: (nextIds: number[]) => replace.mutate(nextIds),
    isLoading: q.isLoading,
    isMutating: add.isPending || remove.isPending || replace.isPending,
  };
}
