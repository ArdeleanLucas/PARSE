import { BrowserRouter } from "react-router-dom";
import { ParseUI } from "./ParseUI";
import { ErrorBoundary } from "./components/shared/ErrorBoundary";

export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <ParseUI />
      </BrowserRouter>
    </ErrorBoundary>
  );
}
