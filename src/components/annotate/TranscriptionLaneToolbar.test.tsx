// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TranscriptionLaneToolbar } from "./TranscriptionLaneToolbar";

afterEach(() => {
  cleanup();
});

describe("TranscriptionLaneToolbar", () => {
  it("renders the lane label, interval span, and full action set for text lanes", () => {
    const onEdit = vi.fn();
    const onSplit = vi.fn();
    const onMerge = vi.fn();
    const onDelete = vi.fn();

    render(
      <TranscriptionLaneToolbar
        end={2.5}
        laneLabel="STT"
        onDelete={onDelete}
        onEdit={onEdit}
        onMerge={onMerge}
        onSplit={onSplit}
        start={1.25}
        x={48}
        y={96}
      />,
    );

    const menu = screen.getByRole("menu");
    expect(menu).toBeTruthy();
    expect(screen.getByText("STT")).toBeTruthy();
    expect(screen.getByText("1.250–2.500s")).toBeTruthy();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Edit text dbl-click" }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Split at playhead S" }));
    expect(onSplit).toHaveBeenCalledTimes(1);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Merge with next" }));
    expect(onMerge).toHaveBeenCalledTimes(1);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Delete" }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("omits the edit action for boundary-only lanes", () => {
    render(
      <TranscriptionLaneToolbar
        end={4}
        laneLabel="BND"
        onDelete={vi.fn()}
        onEdit={null}
        onMerge={vi.fn()}
        onSplit={vi.fn()}
        start={3}
        x={10}
        y={20}
      />,
    );

    const menu = screen.getByRole("menu");
    expect(within(menu).queryByRole("menuitem", { name: "Edit text dbl-click" })).toBeNull();
    expect(within(menu).getByRole("menuitem", { name: "Split at playhead S" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Merge with next" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Delete" })).toBeTruthy();
  });

  it("keeps mouse-downs inside the toolbar from bubbling to the document", () => {
    const onMouseDown = vi.fn();
    document.addEventListener("mousedown", onMouseDown);

    try {
      const { getByRole } = render(
        <TranscriptionLaneToolbar
          end={1}
          laneLabel="IPA"
          onDelete={vi.fn()}
          onEdit={vi.fn()}
          onMerge={vi.fn()}
          onSplit={vi.fn()}
          start={0.5}
          x={32}
          y={64}
        />,
      );

      fireEvent.mouseDown(getByRole("menu"));
      expect(onMouseDown).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener("mousedown", onMouseDown);
    }
  });
});
