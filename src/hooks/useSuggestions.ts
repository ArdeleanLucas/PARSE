import { useEffect, useRef, useState, useCallback } from "react"
import { requestSuggestions } from "../api/client"

export interface Suggestion {
  rank: number
  start_sec: number
  end_sec: number
  confidence_score: number
  match_method: string
  transcript_snippet?: string
  source_wav?: string
}

export interface SpeakerSuggestions {
  [conceptId: string]: {
    speakers: { [speaker: string]: Suggestion[] }
    positional_anchors?: { [speaker: string]: { start_sec: number } }
  }
}

interface UseSuggestionsOptions {
  speaker: string | null
  conceptId: string | null
}

interface UseSuggestionsResult {
  suggestions: Suggestion[]
  loading: boolean
  error: string | null
  priorSpeakers: string[]
  selectedPriors: string[]
  setSelectedPriors: (p: string[]) => void
  expectedTimeSec: number | null
  refresh: () => void
}

const STORAGE_KEY = "se-suggestions-priors"
const MAX_BOOST = 0.25
const SIGMA = 45
const CUTOFF = 120

function loadPriors(speaker: string): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed[speaker]) ? parsed[speaker] : []
  } catch {
    return []
  }
}

function savePriors(speaker: string, priors: string[]) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    parsed[speaker] = priors
    localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed))
  } catch {
    // ignore
  }
}

function gaussianBoost(timeDelta: number): number {
  if (timeDelta > CUTOFF) return 0
  return MAX_BOOST * Math.exp(-0.5 * (timeDelta / SIGMA) ** 2)
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid]
}

export function useSuggestions({
  speaker,
  conceptId,
}: UseSuggestionsOptions): UseSuggestionsResult {
  const [rawData, setRawData] = useState<SpeakerSuggestions | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedPriors, setSelectedPriorsState] = useState<string[]>(() =>
    speaker ? loadPriors(speaker) : [],
  )
  const abortRef = useRef<AbortController | null>(null)
  const [fetchTrigger, setFetchTrigger] = useState(0)

  const setSelectedPriors = useCallback(
    (p: string[]) => {
      setSelectedPriorsState(p)
      if (speaker) savePriors(speaker, p)
    },
    [speaker],
  )

  // Reset selectedPriors when speaker changes
  useEffect(() => {
    if (speaker) {
      setSelectedPriorsState(loadPriors(speaker))
    } else {
      setSelectedPriorsState([])
    }
  }, [speaker])

  // Fetch suggestions
  useEffect(() => {
    if (!speaker || !conceptId) {
      setRawData(null)
      setLoading(false)
      setError(null)
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)

    requestSuggestions(speaker, [conceptId])
      .then((data) => {
        if (controller.signal.aborted) return
        setRawData(data as unknown as SpeakerSuggestions)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : "Failed to fetch suggestions")
        setLoading(false)
      })

    return () => {
      controller.abort()
    }
  }, [speaker, conceptId, fetchTrigger])

  const refresh = useCallback(() => {
    setFetchTrigger((n) => n + 1)
  }, [])

  // Derive suggestions and priors from raw data
  let suggestions: Suggestion[] = []
  let priorSpeakers: string[] = []
  let expectedTimeSec: number | null = null

  if (rawData && conceptId && speaker) {
    const conceptData = rawData[conceptId]
    if (conceptData) {
      suggestions = conceptData.speakers?.[speaker] ?? []
      const anchors = conceptData.positional_anchors
      if (anchors) {
        priorSpeakers = Object.keys(anchors)
      }

      // Compute expected time from selected priors
      if (anchors && selectedPriors.length > 0) {
        const times = selectedPriors
          .filter((sp) => anchors[sp])
          .map((sp) => anchors[sp].start_sec)
        expectedTimeSec = median(times)
      }

      // Rerank with Gaussian boost
      if (expectedTimeSec !== null) {
        const expected = expectedTimeSec
        suggestions = [...suggestions]
          .map((s) => ({
            ...s,
            _boosted: s.confidence_score + gaussianBoost(Math.abs(s.start_sec - expected)),
          }))
          .sort((a, b) => b._boosted - a._boosted)
          .map(({ _boosted: _, ...rest }, i) => ({ ...rest, rank: i + 1 }))
      } else {
        suggestions = [...suggestions].sort(
          (a, b) => b.confidence_score - a.confidence_score,
        )
      }
    }
  }

  return {
    suggestions,
    loading,
    error,
    priorSpeakers,
    selectedPriors,
    setSelectedPriors,
    expectedTimeSec,
    refresh,
  }
}
