import { useState, useCallback } from "react"
import { useAnnotationStore } from "../stores/annotationStore"
import type { AnnotationRecord } from "../api/types"

export interface UseImportExportResult {
  exportTextGrid: (speaker: string) => void
  exportCSV: (speaker: string) => void
  importTextGrid: (speaker: string, file: File) => Promise<void>
  exporting: boolean
  importing: boolean
  error: string | null
}

function triggerDownload(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function buildTextGrid(record: AnnotationRecord): string {
  const tierNames = Object.keys(record.tiers)
  const lines: string[] = []
  lines.push('File type = "ooTextFile"')
  lines.push('Object class = "TextGrid"')
  lines.push("")

  // Compute xmin/xmax across all tiers
  let xmin = 0
  let xmax = 0
  for (const tier of Object.values(record.tiers)) {
    for (const iv of tier.intervals) {
      if (iv.end > xmax) xmax = iv.end
    }
  }

  lines.push(`xmin = ${xmin}`)
  lines.push(`xmax = ${xmax}`)
  lines.push("tiers? <exists>")
  lines.push(`size = ${tierNames.length}`)
  lines.push("item []:")

  tierNames.forEach((name, tierIdx) => {
    const tier = record.tiers[name]
    lines.push(`    item [${tierIdx + 1}]:`)
    lines.push(`        class = "IntervalTier"`)
    lines.push(`        name = "${tier.name}"`)
    lines.push(`        xmin = ${xmin}`)
    lines.push(`        xmax = ${xmax}`)
    lines.push(`        intervals: size = ${tier.intervals.length}`)
    tier.intervals.forEach((iv, ivIdx) => {
      lines.push(`        intervals [${ivIdx + 1}]:`)
      lines.push(`            xmin = ${iv.start}`)
      lines.push(`            xmax = ${iv.end}`)
      lines.push(`            text = "${iv.text.replace(/"/g, '""')}"`)
    })
  })

  return lines.join("\n")
}

function buildCSV(record: AnnotationRecord): string {
  const lines: string[] = ["start,end,ipa,ortho,concept"]
  const ipaTier = record.tiers["ipa"]
  const orthoTier = record.tiers["ortho"]
  const conceptTier = record.tiers["concept"]

  // Use IPA tier as the primary; fall back to whichever has intervals
  const primary = ipaTier ?? orthoTier ?? conceptTier
  if (!primary) return lines.join("\n")

  const count = primary.intervals.length
  for (let i = 0; i < count; i++) {
    const iv = primary.intervals[i]
    const ipa = ipaTier?.intervals[i]?.text ?? ""
    const ortho = orthoTier?.intervals[i]?.text ?? ""
    const concept = conceptTier?.intervals[i]?.text ?? ""
    lines.push(`${iv.start},${iv.end},${csvEscape(ipa)},${csvEscape(ortho)},${csvEscape(concept)}`)
  }
  return lines.join("\n")
}

function csvEscape(val: string): string {
  if (val.includes(",") || val.includes('"') || val.includes("\n")) {
    return `"${val.replace(/"/g, '""')}"`
  }
  return val
}

interface ParsedInterval {
  tier: string
  start: number
  end: number
  text: string
}

function parseTextGrid(content: string): ParsedInterval[] {
  const intervals: ParsedInterval[] = []
  const lines = content.split("\n")
  let currentTier = ""
  let xmin: number | null = null
  let xmax: number | null = null
  let text: string | null = null

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()

    const nameMatch = line.match(/^name\s*=\s*"(.+)"$/i)
    if (nameMatch) {
      currentTier = nameMatch[1].toLowerCase()
      continue
    }

    const xminMatch = line.match(/^xmin\s*=\s*(.+)$/i)
    if (xminMatch && currentTier) {
      xmin = parseFloat(xminMatch[1])
      continue
    }

    const xmaxMatch = line.match(/^xmax\s*=\s*(.+)$/i)
    if (xmaxMatch && currentTier) {
      xmax = parseFloat(xmaxMatch[1])
      continue
    }

    const textMatch = line.match(/^text\s*=\s*"(.*)"$/i)
    if (textMatch && currentTier) {
      text = textMatch[1].replace(/""/g, '"')
      if (xmin !== null && xmax !== null && text !== null) {
        intervals.push({ tier: currentTier, start: xmin, end: xmax, text })
      }
      xmin = null
      xmax = null
      text = null
      continue
    }
  }

  return intervals
}

export function useImportExport(): UseImportExportResult {
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const exportTextGrid = useCallback((speaker: string) => {
    setError(null)
    setExporting(true)
    try {
      const record = useAnnotationStore.getState().records[speaker]
      if (!record) {
        setError(`No annotations loaded for speaker: ${speaker}`)
        return
      }
      const content = buildTextGrid(record)
      triggerDownload(`${speaker}.TextGrid`, content, "text/plain")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed")
    } finally {
      setExporting(false)
    }
  }, [])

  const exportCSV = useCallback((speaker: string) => {
    setError(null)
    setExporting(true)
    try {
      const record = useAnnotationStore.getState().records[speaker]
      if (!record) {
        setError(`No annotations loaded for speaker: ${speaker}`)
        return
      }
      const content = buildCSV(record)
      triggerDownload(`${speaker}.csv`, content, "text/csv")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed")
    } finally {
      setExporting(false)
    }
  }, [])

  const importTextGrid = useCallback(async (speaker: string, file: File) => {
    setError(null)
    setImporting(true)
    try {
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result as string)
        reader.onerror = () => reject(new Error("Failed to read file"))
        reader.readAsText(file)
      })
      if (!content.includes("TextGrid")) {
        throw new Error("Invalid TextGrid file")
      }
      const parsed = parseTextGrid(content)
      if (parsed.length === 0) {
        throw new Error("No intervals found in TextGrid file")
      }
      const { addInterval } = useAnnotationStore.getState()
      for (const iv of parsed) {
        addInterval(speaker, iv.tier, {
          start: iv.start,
          end: iv.end,
          text: iv.text,
        })
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Import failed"
      setError(msg)
      throw e
    } finally {
      setImporting(false)
    }
  }, [])

  return { exportTextGrid, exportCSV, importTextGrid, exporting, importing, error }
}
