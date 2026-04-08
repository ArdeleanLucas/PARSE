import React from "react";
import { Link, useLocation } from "react-router-dom";

interface TopBarProps {
  children?: React.ReactNode;
}

export function TopBar({ children }: TopBarProps = {}) {
  const { pathname } = useLocation();
  const isAnnotate = pathname === "/" || pathname === "/annotate";
  const isCompare = pathname === "/compare";

  return (
    <nav
      style={{
        display: "flex",
        alignItems: "center",
        padding: "0 1rem",
        height: "2.5rem",
        background: "#111827",
        color: "#f9fafb",
        fontFamily: "monospace",
        fontSize: "0.875rem",
        gap: "1.5rem",
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}
    >
      <span style={{ fontWeight: 700, letterSpacing: "0.05em" }}>PARSE</span>
      <Link
        to="/"
        style={{
          color: isAnnotate ? "#60a5fa" : "#9ca3af",
          textDecoration: "none",
          fontWeight: isAnnotate ? 600 : 400,
        }}
      >
        Annotate
      </Link>
      <Link
        to="/compare"
        style={{
          color: isCompare ? "#60a5fa" : "#9ca3af",
          textDecoration: "none",
          fontWeight: isCompare ? 600 : 400,
        }}
      >
        Compare
      </Link>
      {children && (
        <div style={{ marginLeft: "auto" }}>{children}</div>
      )}
    </nav>
  );
}
