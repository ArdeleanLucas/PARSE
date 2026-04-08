import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AnnotateMode } from "./components/annotate/AnnotateMode";
import { CompareMode } from "./components/compare/CompareMode";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AnnotateMode />} />
        <Route path="/compare" element={<CompareMode />} />
      </Routes>
    </BrowserRouter>
  );
}
