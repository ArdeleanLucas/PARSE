// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useImportExport } from "../useImportExport"

const mockAddInterval = vi.fn()
const mockRecords: Record<string, unknown> = {}

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: {
    getState: () => ({
      records: mockRecords,
      addInterval: mockAddInterval,
    }),
  },
}))

describe("useImportExport", () => {
  let anchorClicked: boolean
  let downloadFilename: string

  beforeEach(() => {
    vi.restoreAllMocks()
    mockAddInterval.mockClear()
    anchorClicked = false
    downloadFilename = ""

    // Stub anchor element for download
    const origCreateElement = document.createElement.bind(document)
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        const a = origCreateElement("a") as HTMLAnchorElement
        Object.defineProperty(a, "click", {
          value: () => {
            anchorClicked = true
            downloadFilename = a.download
          },
        })
        return a
      }
      return origCreateElement(tag)
    })

    // Stub URL methods (not available in jsdom)
    URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url")
    URL.revokeObjectURL = vi.fn()
  })

  it("exportTextGrid triggers download", () => {
    Object.assign(mockRecords, {
      SPK_01: {
        speaker: "SPK_01",
        tiers: {
          ipa: {
            name: "ipa",
            display_order: 1,
            intervals: [{ start: 0, end: 1.5, text: "hello" }],
          },
        },
        created_at: "2026-01-01",
        modified_at: "2026-01-01",
        source_wav: "",
      },
    })

    const { result } = renderHook(() => useImportExport())
    act(() => {
      result.current.exportTextGrid("SPK_01")
    })

    expect(anchorClicked).toBe(true)
    expect(downloadFilename).toBe("SPK_01.TextGrid")
  })

  it("exportCSV triggers download", () => {
    Object.assign(mockRecords, {
      SPK_01: {
        speaker: "SPK_01",
        tiers: {
          ipa: {
            name: "ipa",
            display_order: 1,
            intervals: [{ start: 0, end: 1.5, text: "hello" }],
          },
          ortho: {
            name: "ortho",
            display_order: 2,
            intervals: [{ start: 0, end: 1.5, text: "hi" }],
          },
          concept: {
            name: "concept",
            display_order: 3,
            intervals: [{ start: 0, end: 1.5, text: "greeting" }],
          },
        },
        created_at: "2026-01-01",
        modified_at: "2026-01-01",
        source_wav: "",
      },
    })

    const { result } = renderHook(() => useImportExport())
    act(() => {
      result.current.exportCSV("SPK_01")
    })

    expect(anchorClicked).toBe(true)
    expect(downloadFilename).toBe("SPK_01.csv")
  })

  it("importTextGrid calls addInterval for each parsed interval", async () => {
    // Clean records so speaker has a record in store
    for (const k of Object.keys(mockRecords)) delete mockRecords[k]

    const textGridContent = [
      'File type = "ooTextFile"',
      'Object class = "TextGrid"',
      "",
      "xmin = 0",
      "xmax = 3",
      "tiers? <exists>",
      "size = 1",
      "item []:",
      "    item [1]:",
      '        class = "IntervalTier"',
      '        name = "IPA"',
      "        xmin = 0",
      "        xmax = 3",
      "        intervals: size = 2",
      "        intervals [1]:",
      "            xmin = 0",
      "            xmax = 1.5",
      '            text = "word1"',
      "        intervals [2]:",
      "            xmin = 1.5",
      "            xmax = 3",
      '            text = "word2"',
    ].join("\n")

    const file = new File([textGridContent], "test.TextGrid", {
      type: "text/plain",
    })

    const { result } = renderHook(() => useImportExport())
    await act(async () => {
      await result.current.importTextGrid("SPK_01", file)
    })

    expect(mockAddInterval).toHaveBeenCalledTimes(2)
    expect(mockAddInterval).toHaveBeenCalledWith("SPK_01", "ipa", {
      start: 0,
      end: 1.5,
      text: "word1",
    })
    expect(mockAddInterval).toHaveBeenCalledWith("SPK_01", "ipa", {
      start: 1.5,
      end: 3,
      text: "word2",
    })
  })

  it("error state on bad TextGrid file", async () => {
    const file = new File(["not a textgrid"], "bad.TextGrid", {
      type: "text/plain",
    })

    const { result } = renderHook(() => useImportExport())

    let caught: Error | null = null
    await act(async () => {
      try {
        await result.current.importTextGrid("SPK_01", file)
      } catch (e) {
        caught = e as Error
      }
    })

    expect(caught).toBeTruthy()
    expect(result.current.error).toBe("Invalid TextGrid file")
  })
})
