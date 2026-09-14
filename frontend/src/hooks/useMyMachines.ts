// §10.4 내 머신 — 아카이브(1,400+대)에서 골라 담은 사용자별 목록. 종목 폼·설정 화면 공용.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addMyMachine, fetchMyMachines, removeMyMachine } from "../api/client";
import type { Machine } from "../api/types";

const KEY = ["my-machines"];

export function useMyMachines() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: fetchMyMachines, staleTime: 60_000 });
  const machines = q.data ?? [];
  const idSet = new Set(machines.map((m) => m.id));

  const apply = (data: Machine[]) => qc.setQueryData(KEY, data);
  const add = useMutation({ mutationFn: addMyMachine, onSuccess: apply });
  const remove = useMutation({ mutationFn: removeMyMachine, onSuccess: apply });

  return {
    machines,
    has: (machineId: number) => idSet.has(machineId),
    add: (machineId: number) => add.mutateAsync(machineId),
    remove: (machineId: number) => remove.mutate(machineId),
    isLoading: q.isLoading,
    isMutating: add.isPending || remove.isPending,
  };
}
