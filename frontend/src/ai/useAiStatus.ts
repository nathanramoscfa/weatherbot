// frontend/src/ai/useAiStatus.ts
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../api/keys.ts";
import { fetchAiStatus } from "./queries.ts";

export function useAiStatus() {
  return useQuery({
    queryKey: queryKeys.ai(),
    queryFn: fetchAiStatus,
  });
}
