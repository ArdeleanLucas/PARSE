// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { OnboardingFlow } from "./OnboardingFlow"

let mockConfig: {
  project_name: string
  language_code: string
  speakers: string[]
  concepts: { id: string; label: string }[]
  audio_dir: string
  annotations_dir: string
} | null = {
  project_name: "Test Project",
  language_code: "sdh",
  speakers: ["SPK_01", "SPK_02"],
  concepts: [],
  audio_dir: "audio",
  annotations_dir: "annotations",
}

const mockLoad = vi.fn().mockResolvedValue(undefined)

vi.mock("../../stores/configStore", () => ({
  useConfigStore: (
    selector: (s: { config: typeof mockConfig; load: () => Promise<void>; loading: boolean }) => unknown,
  ) => selector({ config: mockConfig, load: mockLoad, loading: false }),
}))

const mockSetState = vi.fn()
vi.mock("../../stores/uiStore", () => ({
  useUIStore: {
    setState: (...args: unknown[]) => mockSetState(...args),
  },
}))

describe("OnboardingFlow", () => {
  const onComplete = vi.fn()

  beforeEach(() => {
    vi.useFakeTimers()
    mockConfig = {
      project_name: "Test Project",
      language_code: "sdh",
      speakers: ["SPK_01", "SPK_02"],
      concepts: [],
      audio_dir: "audio",
      annotations_dir: "annotations",
    }
    onComplete.mockClear()
    mockSetState.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
    cleanup()
  })

  it("renders welcome step", () => {
    render(<OnboardingFlow onComplete={onComplete} />)
    expect(
      screen.getByText("PARSE — Phonetic Analysis and Review Source Explorer"),
    ).toBeTruthy()
    expect(screen.getByText(/Test Project/)).toBeTruthy()
    expect(screen.getByText("Welcome")).toBeTruthy()
  })

  it("Next advances step", () => {
    render(<OnboardingFlow onComplete={onComplete} />)
    fireEvent.click(screen.getByText("Next"))
    expect(screen.getByText("Config check")).toBeTruthy()
    expect(screen.getByText(/sdh/)).toBeTruthy()
  })

  it("speaker selection enables Start button", () => {
    render(<OnboardingFlow onComplete={onComplete} />)
    // Advance to step 1
    fireEvent.click(screen.getByText("Next"))
    // Advance to step 2
    fireEvent.click(screen.getByText("Next"))
    const startBtn = screen.getByText("Start annotating")
    expect(startBtn).toBeTruthy()
    expect((startBtn as HTMLButtonElement).disabled).toBe(true)

    // Select a speaker
    const select = screen.getByRole("combobox")
    fireEvent.change(select, { target: { value: "SPK_01" } })
    expect((startBtn as HTMLButtonElement).disabled).toBe(false)
  })
})
