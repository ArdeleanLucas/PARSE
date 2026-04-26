import { Button } from "../../shared/Button";
import { GROUP_COLORS } from "./shared";
import { GROUP_LETTERS, type GroupLetter, type Mode } from "./types";

export function CognateActionMenu({
  mode,
  splitTarget,
  setSplitTarget,
  handleAccept,
  handleMerge,
  handleSplitToggle,
  handleCycleToggle,
  handleDoneSplit,
}: {
  mode: Mode;
  splitTarget: GroupLetter;
  setSplitTarget: (target: GroupLetter) => void;
  handleAccept: () => Promise<void>;
  handleMerge: () => Promise<void>;
  handleSplitToggle: () => void;
  handleCycleToggle: () => void;
  handleDoneSplit: () => Promise<void>;
}) {
  return (
    <>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
        <Button size="sm" onClick={() => void handleAccept()}>Accept</Button>
        <Button size="sm" variant={mode === "split" ? "primary" : "secondary"} onClick={handleSplitToggle}>Split</Button>
        <Button size="sm" onClick={() => void handleMerge()}>Merge</Button>
        <Button size="sm" variant={mode === "cycle" ? "primary" : "secondary"} onClick={handleCycleToggle}>Cycle</Button>
      </div>

      {mode === "split" && (
        <div style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontSize: "0.75rem", color: "#6b7280", marginBottom: "0.25rem" }}>Target group:</div>
          <div style={{ display: "flex", gap: "0.25rem", marginBottom: "0.5rem" }}>
            {GROUP_LETTERS.map((letter) => (
              <button
                key={letter}
                onClick={() => setSplitTarget(letter)}
                style={{
                  padding: "0.125rem 0.5rem",
                  borderRadius: "0.25rem",
                  border: splitTarget === letter ? "2px solid #3b82f6" : "1px solid #d1d5db",
                  background: GROUP_COLORS[letter],
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                  fontWeight: splitTarget === letter ? 700 : 400,
                }}
              >
                {letter}
              </button>
            ))}
          </div>
          <Button size="sm" onClick={() => void handleDoneSplit()}>Done Split</Button>
        </div>
      )}
    </>
  );
}
