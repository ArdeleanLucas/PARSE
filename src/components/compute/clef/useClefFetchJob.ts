import { useCallback, useEffect, useState } from "react";
import { startContactLexemeFetch } from "../../../api/client";

export function useClefFetchJob(providerIds: string[]) {
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(new Set());
  const [overwrite, setOverwrite] = useState(false);
  const [populateFailed, setPopulateFailed] = useState(false);

  useEffect(() => {
    if (providerIds.length === 0) return;
    setSelectedProviders((prev) => prev.size > 0 ? prev : new Set(providerIds));
  }, [providerIds]);

  const toggleProvider = useCallback((providerId: string) => {
    setSelectedProviders((prev) => {
      const next = new Set(prev);
      if (next.has(providerId)) next.delete(providerId);
      else next.add(providerId);
      return next;
    });
  }, []);

  const selectProvider = useCallback((providerId: string) => {
    setSelectedProviders((prev) => {
      if (prev.has(providerId)) return prev;
      const next = new Set(prev);
      next.add(providerId);
      return next;
    });
  }, []);

  const startPopulate = useCallback(async (languages: string[], providerSubset?: string[]) => {
    const requestedProviders = providerSubset ?? Array.from(selectedProviders);
    const job = await startContactLexemeFetch({
      languages,
      providers: requestedProviders.length > 0 ? requestedProviders : undefined,
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
    selectProvider,
    setOverwrite,
    setPopulateFailed,
    startPopulate,
    toggleProvider,
  };
}
