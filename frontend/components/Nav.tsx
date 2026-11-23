"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { apiJson } from "@/lib/api";

function Icon({ name }: { name: string }) {
  const p = {
    viewBox: "0 0 24 24",
    width: 16,
    height: 16,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  switch (name) {
    case "agent":
      return (
        <svg {...p}>
          <path d="M12 2a3 3 0 0 0-3 3v1H7a3 3 0 0 0-3 3v7a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V9a3 3 0 0 0-3-3h-2V5a3 3 0 0 0-3-3Z" />
          <circle cx="9.5" cy="12.5" r="1" />
          <circle cx="14.5" cy="12.5" r="1" />
        </svg>
      );
    case "workbench":
      return (
        <svg {...p}>
          <path d="M4 19h16M7 15V9m5 6V5m5 10v-4" />
        </svg>
      );
    case "pathway":
      return (
        <svg {...p}>
          <circle cx="6" cy="6" r="2.5" />
          <circle cx="18" cy="6" r="2.5" />
          <circle cx="12" cy="18" r="2.5" />
          <path d="M8.2 7.5 11 15.8M15.8 7.5 13 15.8M8.5 6h7" />
        </svg>
      );
    case "target":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "compound":
      return (
        <svg {...p}>
          <path d="m10 3-6.5 6.5a4.6 4.6 0 0 0 6.5 6.5L16.5 9.5A4.6 4.6 0 0 0 10 3Z" />
          <path d="m8.5 8.5 7 7" />
        </svg>
      );
    case "structure":
      return (
        <svg {...p}>
          <polygon points="12 3 19 7 19 15 12 19 5 15 5 7" />
        </svg>
      );
    case "cases":
      return (
        <svg {...p}>
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M8 9h8M8 13h8M8 17h5" />
        </svg>
      );
    case "downloads":
      return (
        <svg {...p}>
          <path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14" />
        </svg>
      );
    default:
      return (
        <svg {...p}>
          <path d="M6 4h9l3 3v13H6z" />
          <path d="M9 12h6M9 16h4" />
        </svg>
      );
  }
}

const LINKS = [
  ["/", "Agent Console", "agent"],
  ["/workbench", "Signature Workbench", "workbench"],
  ["/pathway-tf", "Pathway & TF Search", "pathway"],
  ["/target", "Target & Genetics", "target"],
  ["/compound", "Compound Explorer", "compound"],
  ["/structure", "Structure Search", "structure"],
  ["/cases", "Disease Cohorts", "cases"],
  ["/downloads", "Downloads", "downloads"],
  ["/docs", "API & MCP Docs", "docs"],
] as const;

export default function Nav() {
  const path = usePathname() || "/";
  const [health, setHealth] = useState<any>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    apiJson("/health", undefined, 10000)
      .then(setHealth)
      .catch(() => setOffline(true));
  }, []);

  const active = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);

  return (
    <aside className="sidebar">
      <div className="brand-wrap">
        <img
          src="/logo.svg"
          alt="NephroPerturb logo"
          width={34}
          height={34}
          className="brand-logo"
        />
        <div className="brand">
          Nephro<span>Perturb</span>
        </div>
      </div>
      <div className="tagline">
        Kidney drug-perturbation knowledge base · 21,299 compounds · 12,328 genes
      </div>
      <nav className="nav">
        {LINKS.map(([href, label, icon]) => (
          <Link
            key={href}
            href={href}
            prefetch={false}
            className={active(href) ? "active" : ""}
          >
            <Icon name={icon} />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-foot">
        <span className={`status-dot ${health ? "online" : ""}`} />
        <span>
          {health
            ? `v${health.version || "1.1.0"} · ${health.mode === "lite" ? "Lite 1-core" : "Full mode"}`
            : offline
            ? "API offline"
            : "Connecting..."}
        </span>
      </div>
    </aside>
  );
}
