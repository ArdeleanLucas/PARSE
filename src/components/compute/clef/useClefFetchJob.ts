import { useCallback, useState } from "react";
import { startContactLexemeFetch } from "../../../api/client";

export function useClefFetchJob() {
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(new Set());
  const [overwrite, setOverwrite] = useState(false);
  const [populateFailed, setPopulateFailed] = useState(false);

  const toggleProvider = useCallback((providerId: string) => {
    setSelectedProviders((prev) => {
      const next = new Set(prev);
      if (next.has(providerId)) next.delete(providerId);
      else next.add(providerId);
      return next;
    });
  }, []);

  const startPopulate = useCallback(async (languages: string[]) => {
    const job = await startContactLexemeFetch({
      languages,
      providers: selectedProviders.size > 0 ? Array.from(selectedProviders) : undefined,
      overwrite,
    });
    const id = job.jobId || job.job_id || "";
    if (!id) throw new Error("No job id returned");
    setPopulateFailed(false);
    return id;
  }, [overwrite, selectedProviders]);

  return {
    overwrite,
    populateFailed,
    selectedProviders,
    setOverwrite,
    setPopulateFailed,
    startPopulate,
    toggleProvider,
  };
}
