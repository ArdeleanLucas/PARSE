import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { AnnotateMode } from "./components/annotate/AnnotateMode";

function ComparePlaceholder() {
  return (
    <div style={{ padding: "2rem", fontFamily: "monospace" }}>
      <h1>PARSE — Compare Mode</h1>
      <p>Phase 0 scaffold. Track B implementation in progress.</p>
      <Link to="/">Go to Annotate Mode</Link>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AnnotateMode />} />
        <Route path="/compare" element={<ComparePlaceholder />} />
      </Routes>
    </BrowserRouter>
  );
}
