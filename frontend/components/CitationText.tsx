"use client";
import React from "react";

const TOKEN_RE =
  /(\[PMID:\s*\d{5,9}\]|\[NCT\d{8}\]|\*\*[^*]+\*\*|`[^`]+`)/g;

function renderInline(line: string, keyPrefix: string): React.ReactNode[] {
  const parts = line.split(TOKEN_RE);
  return parts.map((part, idx) => {
    const k = `${keyPrefix}-${idx}`;
    const pmidMatch = part.match(/^\[PMID:\s*(\d{5,9})\]$/i);
    if (pmidMatch) {
      const id = pmidMatch[1];
      return (
        <a
          key={k}
          href={`https://pubmed.ncbi.nlm.nih.gov/${id}/`}
          target="_blank"
          rel="noopener noreferrer"
          className="cite-chip cite-pmid"
          title={`Open PMID ${id} on PubMed`}
        >
          PMID:{id}
        </a>
      );
    }
    const nctMatch = part.match(/^\[(NCT\d{8})\]$/i);
    if (nctMatch) {
      const id = nctMatch[1].toUpperCase();
      return (
        <a
          key={k}
          href={`https://clinicaltrials.gov/study/${id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="cite-chip cite-nct"
          title={`Open ${id} on ClinicalTrials.gov`}
        >
          {id}
        </a>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={k}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={k} className="inline-code">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={k}>{part}</React.Fragment>;
  });
}

export default function CitationText({ text }: { text: string }) {
  if (!text) return null;
  const lines = text.split(/\r?\n/);

  return (
    <div className="cite-text">
      {lines.map((rawLine, idx) => {
        const line = rawLine.trim();
        if (!line) return <div key={`sp-${idx}`} style={{ height: 5 }} />;
        if (line.startsWith("### ") || line.startsWith("## ")) {
          const clean = line.replace(/^#{2,3}\s+/, "");
          return (
            <div key={`h-${idx}`} className="cite-heading">
              {renderInline(clean, `h-${idx}`)}
            </div>
          );
        }
        if (line.startsWith("- ") || line.startsWith("* ")) {
          return (
            <div key={`li-${idx}`} className="cite-bullet">
              <span className="cite-dot">•</span>
              <div>{renderInline(line.slice(2), `li-${idx}`)}</div>
            </div>
          );
        }
        return (
          <div key={`p-${idx}`} className="cite-para">
            {renderInline(line, `p-${idx}`)}
          </div>
        );
      })}
    </div>
  );
}
