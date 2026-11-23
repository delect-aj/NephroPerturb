"use client";
import React from "react";

const TOKEN_RE =
  /(\[PMID:\s*\d{5,9}\]|\[NCT\d{8}\]|\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)/g;

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
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={k}>{part.slice(1, -1)}</em>;
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

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

function isSeparatorRow(line: string): boolean {
  return /^\|?(\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$/.test(line.trim());
}

export default function CitationText({ text }: { text: string }) {
  if (!text) return null;
  const lines = text.split(/\r?\n/);
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const rawLine = lines[i];
    const line = rawLine.trim();
    if (!line) {
      i += 1;
      continue;
    }

    // Markdown table block
    if (line.includes("|") && i + 1 < lines.length && isSeparatorRow(lines[i + 1])) {
      const headers = splitTableRow(line);
      const bodyRows: string[][] = [];
      let j = i + 2;
      while (j < lines.length && lines[j].trim().includes("|") && lines[j].trim() !== "") {
        bodyRows.push(splitTableRow(lines[j]));
        j += 1;
      }
      nodes.push(
        <div key={`tbl-${i}`} className="cite-table-wrap">
          <table>
            <thead>
              <tr>
                {headers.map((h, hIdx) => (
                  <th key={`th-${i}-${hIdx}`}>{renderInline(h, `th-${i}-${hIdx}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((row, rIdx) => (
                <tr key={`tr-${i}-${rIdx}`}>
                  {headers.map((_, cIdx) => (
                    <td key={`td-${i}-${rIdx}-${cIdx}`}>
                      {renderInline(row[cIdx] || "—", `td-${i}-${rIdx}-${cIdx}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = j;
      continue;
    }

    // Section heading (### / ##)
    if (line.startsWith("### ") || line.startsWith("## ")) {
      const clean = line.replace(/^#{2,3}\s+/, "");
      nodes.push(
        <div key={`h-${i}`} className="cite-section-h">
          {renderInline(clean, `h-${i}`)}
        </div>
      );
      i += 1;
      continue;
    }

    // Bullet item
    if (line.startsWith("- ") || line.startsWith("* ")) {
      nodes.push(
        <div key={`li-${i}`} className="cite-bullet">
          <span className="cite-dot">•</span>
          <div>{renderInline(line.slice(2), `li-${i}`)}</div>
        </div>
      );
      i += 1;
      continue;
    }

    // Flowing prose paragraph (merge consecutive plain text lines)
    const paraLines = [line];
    let j = i + 1;
    while (j < lines.length) {
      const nxt = lines[j].trim();
      if (
        !nxt ||
        nxt.startsWith("#") ||
        nxt.startsWith("- ") ||
        nxt.startsWith("* ") ||
        (nxt.includes("|") && j + 1 < lines.length && isSeparatorRow(lines[j + 1]))
      ) {
        break;
      }
      paraLines.push(nxt);
      j += 1;
    }
    nodes.push(
      <p key={`p-${i}`} className="cite-para">
        {renderInline(paraLines.join(" "), `p-${i}`)}
      </p>
    );
    i = j;
  }

  return <div className="cite-text">{nodes}</div>;
}
