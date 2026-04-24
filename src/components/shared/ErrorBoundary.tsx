import React from "react";

interface Props {
  children: React.ReactNode;
}

interface State {
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

/**
 * Root-level error boundary. Without one, an uncaught render error (e.g. a
 * crash in the post-STT reload flow) unmounts the entire tree and Vite HMR
 * presents it as a page refresh — losing in-flight process output and
 * snapping local component state (like the current mode) back to defaults.
 *
 * This boundary catches the error, shows the stack, and lets the user retry
 * without a full reload — so the next time the "phantom refresh" happens
 * we actually see what triggered it.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null, errorInfo: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error("[ErrorBoundary] caught:", error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = (): void => {
    this.setState({ error: null, errorInfo: null });
  };

  render(): React.ReactNode {
    const { error, errorInfo } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        style={{
          minHeight: "100vh",
          padding: "1.5rem",
          fontFamily: "monospace",
          fontSize: "0.875rem",
          background: "#fff5f5",
          color: "#7f1d1d",
          overflow: "auto",
        }}
        role="alert"
      >
        <div style={{ fontWeight: 700, fontSize: "1rem", marginBottom: "0.75rem" }}>
          PARSE hit an unhandled error
        </div>
        <div style={{ marginBottom: "0.5rem", color: "#991b1b" }}>
          The app kept running instead of reloading, so the process output you
          were looking at in the other panels is still intact. Copy the trace
          below and share it — that's what we need to chase the root cause.
        </div>
        <div style={{ marginBottom: "0.5rem" }}>
          <button
            type="button"
            onClick={this.handleReset}
            style={{
              padding: "0.375rem 0.75rem",
              border: "1px solid #991b1b",
              borderRadius: "0.25rem",
              background: "#fee2e2",
              color: "#7f1d1d",
              cursor: "pointer",
              fontFamily: "monospace",
              fontSize: "0.75rem",
            }}
          >
            Try to recover (clears the error, re-renders the tree)
          </button>
        </div>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            background: "#fee2e2",
            border: "1px solid #fca5a5",
            borderRadius: "0.25rem",
            padding: "0.75rem",
            marginTop: "0.5rem",
            maxHeight: "60vh",
            overflow: "auto",
          }}
        >
          {error.message}
          {"\n\n"}
          {error.stack}
          {errorInfo?.componentStack ? "\n\n--- React component stack ---" + errorInfo.componentStack : ""}
        </pre>
      </div>
    );
  }
}
