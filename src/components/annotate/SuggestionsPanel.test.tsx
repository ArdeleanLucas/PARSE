// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { SuggestionsPanel } from "./SuggestionsPanel"

let mockActiveSpeaker: string | null = "SPK_00"
let mockActiveConcept: string | null = "concept-1"

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (
    selector: (s: {
      activeSpeaker: string | null
      activeConcept: string | null
    }) => unknown,
  ) =>
    selector({
      activeSpeaker: mockActiveSpeaker,
      activeConcept: mockActiveConcept,
    }),
}))

const mockSetSelectedPriors = vi.fn()

let mockReturn = {
  suggestions: [] as {
    rank: number
    start_sec: number
    end_sec: number
    confidence_score: number
    match_method: string
    transcript_snippet?: string
    source_wav?: string
  }[],
  loading: false,
  error: null as string | null,
  priorSpeakers: [] as string[],
  selectedPriors: [] as string[],
  setSelectedPriors: mockSetSelectedPriors,
  expectedTimeSec: null as number | null,
  refresh: vi.fn(),
}

vi.mock("../../hooks/useSuggestions", () => ({
  useSuggestions: () => mockReturn,
}))

beforeEach(() => {
  mockActiveSpeaker = "SPK_00"
  mockActiveConcept = "concept-1"
  mockSetSelectedPriors.mockClear()
  mockReturn = {
    suggestions: [],
    loading: false,
    error: null,
    priorSpeakers: [],
    selectedPriors: [],
    setSelectedPriors: mockSetSelectedPriors,
    expectedTimeSec: null,
    refresh: vi.fn(),
  }
})

afterEach(cleanup)

describe("SuggestionsPanel", () => {
  it("renders loading spinner while fetching", () => {
    mockReturn.loading = true
    render(<SuggestionsPanel onSeek={vi.fn()} />)
    expect(screen.getByTestId("loading-spinner")).toBeTruthy()
  })

  it("renders empty state when suggestions is []", () => {
    render(<SuggestionsPanel onSeek={vi.fn()} />)
    expect(screen.getByText("No suggestions for this concept/speaker")).toBeTruthy()
  })

  it("renders suggestion cards with rank and confidence", () => {
    mockReturn.suggestions = [
      {
        rank: 1,
        start_sec: 12.345,
        end_sec: 14.0,
        confidence_score: 0.9,
        match_method: "dtw",
        transcript_snippet: "hello world",
      },
      {
        rank: 2,
        start_sec: 30.0,
        end_sec: 32.0,
        confidence_score: 0.4,
        match_method: "cosine",
      },
    ]
    render(<SuggestionsPanel onSeek={vi.fn()} />)
    const cards = screen.getAllByTestId("suggestion-card")
    expect(cards).toHaveLength(2)
    expect(screen.getByText("#1")).toBeTruthy()
    expect(screen.getByText("high")).toBeTruthy()
    expect(screen.getByText("#2")).toBeTruthy()
    expect(screen.getByText("low")).toBeTruthy()
  })

  it("clicking a suggestion card calls onSeek with correct args", () => {
    const onSeek = vi.fn()
    mockReturn.suggestions = [
      {
        rank: 1,
        start_sec: 5.0,
        end_sec: 8.0,
        confidence_score: 0.7,
        match_method: "dtw",
      },
    ]
    render(<SuggestionsPanel onSeek={onSeek} />)
    fireEvent.click(screen.getByTestId("suggestion-card"))
    expect(onSeek).toHaveBeenCalledWith(5.0, true, 3.0)
  })

  it("clicking Recommended sets all priorSpeakers as selected", () => {
    mockReturn.priorSpeakers = ["SPK_01", "SPK_02"]
    render(<SuggestionsPanel onSeek={vi.fn()} />)
    fireEvent.click(screen.getByText("Recommended"))
    expect(mockSetSelectedPriors).toHaveBeenCalledWith(["SPK_01", "SPK_02"])
  })

  it("clicking Clear empties selectedPriors", () => {
    mockReturn.priorSpeakers = ["SPK_01"]
    mockReturn.selectedPriors = ["SPK_01"]
    render(<SuggestionsPanel onSeek={vi.fn()} />)
    fireEvent.click(screen.getByText("Clear"))
    expect(mockSetSelectedPriors).toHaveBeenCalledWith([])
  })
})
