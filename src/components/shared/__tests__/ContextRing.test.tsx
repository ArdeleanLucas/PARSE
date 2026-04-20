// @vitest-environment jsdom
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ContextRing } from "../ContextRing"

describe("ContextRing", () => {
  it("renders nothing when data is missing", () => {
    const { container } = render(<ContextRing used={null} limit={null} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders nothing when the limit is zero or negative", () => {
    const { container } = render(<ContextRing used={100} limit={0} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders an SVG with both background and fill circles when data is present", () => {
    const { container } = render(<ContextRing used={3200} limit={128000} />)
    const svg = container.querySelector("svg")
    expect(svg).not.toBeNull()
    expect(container.querySelectorAll("circle")).toHaveLength(2)
  })

  it("uses the warning tone when usage crosses 70%", () => {
    const { container } = render(<ContextRing used={90_000} limit={128_000} />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.className).toContain("text-amber-500")
  })

  it("uses the danger tone when usage crosses 90%", () => {
    const { container } = render(<ContextRing used={120_000} limit={128_000} />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.className).toContain("text-rose-500")
  })

  it("puts usage summary in the title for hover tooltip", () => {
    const { container } = render(<ContextRing used={3200} limit={128000} />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.getAttribute("title")).toMatch(/3\.2k/)
    expect(wrapper.getAttribute("title")).toMatch(/128k/)
    expect(wrapper.getAttribute("title")).toMatch(/2%|3%/)
  })
})
