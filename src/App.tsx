import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AnnotateMode } from "./components/annotate/AnnotateMode";
import { CompareMode } from "./components/compare/CompareMode";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AnnotateMode />} />
        <Route path="/compare" element={<CompareMode />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
