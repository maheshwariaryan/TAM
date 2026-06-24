"use client";

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

export function useApiQuery<T extends z.ZodTypeAny>(
  key: string[],
  url: string,
  schema: T
) {
  return useQuery<z.infer<T>>({
    queryKey: key,
    queryFn: async () => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const json = await res.json();
      return schema.parse(json);
    },
  });
}
