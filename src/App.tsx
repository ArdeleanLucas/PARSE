import { BrowserRouter, Routes, Route, Link } from "react-router-dom";

function AnnotatePlaceholder() {
  return (
    <div style={{ padding: "2rem", fontFamily: "monospace" }}>
      <h1>PARSE — Annotate Mode</h1>
      <p>Phase 0 scaffold. Track A implementation in progress.</p>
      <Link to="/compare">Go to Compare Mode</Link>
    </div>
  );
}

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
        <Route path="/" element={<AnnotatePlaceholder />} />
        <Route path="/compare" element={<ComparePlaceholder />} />
      </Routes>
    </BrowserRouter>
  );
}
