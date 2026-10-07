/**
 * FinalResumeComparisonScreen — /comparison
 *
 * Side-by-side diff of the original (v1) and revised resume using diff-match-patch.
 * - Additions highlighted green
 * - Deletions struck through in red
 * - Download controls for .txt and PDF
 *
 * Owner: Shahin
 * Requirements: 9.3, 9.4, 12.7
 */

import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { diff_match_patch, DIFF_INSERT, DIFF_DELETE, DIFF_EQUAL } from "diff-match-patch";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ComparisonProps {
  /** UUID of the original (baseline) ResumeVersion */
  originalVersionId: string;
  /** UUID of the revised ResumeVersion */
  revisedVersionId: string;
}

interface ResumeVersionData {
  content: string;
  version_number: number;
}

// ── API helpers ───────────────────────────────────────────────────────────────

const API_BASE = "/api";

async function fetchVersionContent(versionId: string): Promise<ResumeVersionData> {
  // Download as txt to get the raw content for diff computation
  const res = await fetch(
    `${API_BASE}/resumes/versions/${versionId}/download?format=txt`
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `Failed to fetch version ${versionId}`);
  }
  const text = await res.text();
  // Extract version number from Content-Disposition if available
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/resume_v(\d+)\./);
  const versionNumber = match ? parseInt(match[1], 10) : 0;
  return { content: text, version_number: versionNumber };
}

// ── Download handler ──────────────────────────────────────────────────────────

function downloadVersion(versionId: string, format: "txt" | "pdf"): void {
  const url = `${API_BASE}/resumes/versions/${versionId}/download?format=${format}`;
  const link = document.createElement("a");
  link.href = url;
  link.download = `resume_${versionId}.${format}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// ── Diff renderer ─────────────────────────────────────────────────────────────

/**
 * Split text into sentence-level chunks for a more readable diff.
 * Split pattern: after sentence-ending punctuation followed by whitespace.
 */
function splitIntoSentences(text: string): string {
  // Equivalent of /(?<=[.!?])\s+/ for sentence splitting
  return text.replace(/([.!?])\s+/g, "$1\n").trim();
}

interface DiffSegment {
  type: typeof DIFF_INSERT | typeof DIFF_DELETE | typeof DIFF_EQUAL;
  text: string;
}

function computeDiff(original: string, revised: string): DiffSegment[] {
  const dmp = new diff_match_patch();
  // Use sentence-aware text for cleaner diffs
  const normalOriginal = splitIntoSentences(original);
  const normalRevised = splitIntoSentences(revised);
  const diffs = dmp.diff_main(normalOriginal, normalRevised);
  dmp.diff_cleanupSemantic(diffs);
  return diffs.map(([type, text]) => ({ type, text }));
}

// ── DiffView component ────────────────────────────────────────────────────────

const DiffView: React.FC<{ diffs: DiffSegment[] }> = ({ diffs }) => (
  <div
    style={{
      fontFamily: "monospace",
      fontSize: "0.875rem",
      lineHeight: "1.6",
      whiteSpace: "pre-wrap",
      wordBreak: "break-word",
    }}
    data-testid="diff-view"
  >
    {diffs.map((seg, i) => {
      if (seg.type === DIFF_INSERT) {
        return (
          <mark
            key={i}
            style={{ backgroundColor: "#d4f7d4", color: "#1a5e1a" }}
            data-testid="diff-addition"
          >
            {seg.text}
          </mark>
        );
      }
      if (seg.type === DIFF_DELETE) {
        return (
          <del
            key={i}
            style={{ color: "#c0392b", backgroundColor: "#fdecea" }}
            data-testid="diff-deletion"
          >
            {seg.text}
          </del>
        );
      }
      return <span key={i}>{seg.text}</span>;
    })}
  </div>
);

// ── Main screen ───────────────────────────────────────────────────────────────

const FinalResumeComparisonScreen: React.FC<ComparisonProps> = ({
  originalVersionId,
  revisedVersionId,
}) => {
  // Fetch both versions in parallel
  const originalQuery = useQuery<ResumeVersionData, Error>({
    queryKey: ["resume-version", originalVersionId],
    queryFn: () => fetchVersionContent(originalVersionId),
    enabled: Boolean(originalVersionId),
  });

  const revisedQuery = useQuery<ResumeVersionData, Error>({
    queryKey: ["resume-version", revisedVersionId],
    queryFn: () => fetchVersionContent(revisedVersionId),
    enabled: Boolean(revisedVersionId),
  });

  // Compute diff only when both versions are loaded
  const diffs = useMemo<DiffSegment[]>(() => {
    if (!originalQuery.data || !revisedQuery.data) return [];
    return computeDiff(
      originalQuery.data.content,
      revisedQuery.data.content
    );
  }, [originalQuery.data, revisedQuery.data]);

  const isLoading = originalQuery.isLoading || revisedQuery.isLoading;
  const error = originalQuery.error ?? revisedQuery.error;

  return (
    <div style={{ padding: "1.5rem", maxWidth: "1200px", margin: "0 auto" }}>
      <h1 style={{ marginBottom: "0.5rem" }}>Resume Comparison</h1>
      <p style={{ color: "#555", marginBottom: "1.5rem" }}>
        Changes needed to cross the ATS threshold are highlighted below.{" "}
        <span style={{ color: "#1a5e1a" }}>Green</span> = additions;{" "}
        <span style={{ color: "#c0392b" }}>strikethrough</span> = removals.
      </p>

      {/* Download controls */}
      <div
        style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem" }}
        aria-label="Download controls"
      >
        <button
          onClick={() => downloadVersion(revisedVersionId, "txt")}
          disabled={revisedQuery.isLoading}
          style={{
            padding: "0.5rem 1rem",
            backgroundColor: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
          }}
          data-testid="download-txt"
          aria-label="Download revised resume as plain text"
        >
          Download .txt
        </button>
        <button
          onClick={() => downloadVersion(revisedVersionId, "pdf")}
          disabled={revisedQuery.isLoading}
          style={{
            padding: "0.5rem 1rem",
            backgroundColor: "#16a34a",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
          }}
          data-testid="download-pdf"
          aria-label="Download revised resume as PDF"
        >
          Download PDF
        </button>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div role="status" aria-live="polite" style={{ color: "#555" }}>
          Loading resume versions…
        </div>
      )}

      {/* Error state */}
      {error && (
        <div
          role="alert"
          style={{
            backgroundColor: "#fdecea",
            color: "#c0392b",
            padding: "1rem",
            borderRadius: "4px",
            marginBottom: "1rem",
          }}
        >
          {error.message}
        </div>
      )}

      {/* Side-by-side diff */}
      {!isLoading && !error && originalQuery.data && revisedQuery.data && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
          }}
        >
          {/* Original panel */}
          <section aria-labelledby="original-heading">
            <h2
              id="original-heading"
              style={{ fontSize: "1rem", marginBottom: "0.5rem" }}
            >
              Original Resume (v
              {originalQuery.data.version_number})
            </h2>
            <div
              style={{
                border: "1px solid #ddd",
                borderRadius: "4px",
                padding: "1rem",
                minHeight: "400px",
                backgroundColor: "#fafafa",
                fontFamily: "monospace",
                fontSize: "0.875rem",
                whiteSpace: "pre-wrap",
                overflowY: "auto",
              }}
              data-testid="original-pane"
            >
              {originalQuery.data.content}
            </div>
          </section>

          {/* Revised panel with diff highlighting */}
          <section aria-labelledby="revised-heading">
            <h2
              id="revised-heading"
              style={{ fontSize: "1rem", marginBottom: "0.5rem" }}
            >
              Revised Resume (v
              {revisedQuery.data.version_number})
            </h2>
            <div
              style={{
                border: "1px solid #ddd",
                borderRadius: "4px",
                padding: "1rem",
                minHeight: "400px",
                backgroundColor: "#fafafa",
                overflowY: "auto",
              }}
              data-testid="revised-pane"
            >
              <DiffView diffs={diffs} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
};

export default FinalResumeComparisonScreen;
