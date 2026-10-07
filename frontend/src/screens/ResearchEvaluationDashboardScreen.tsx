/**
 * ResearchEvaluationDashboardScreen — /research
 *
 * Displays aggregate metrics across experiment runs, a grouped bar chart
 * comparing the three baseline methods, and a paginated run table.
 *
 * Components:
 *   - ExperimentFilters  — filter controls (baseline method, date, threshold, model)
 *   - AggregateMetricsPanel — flip rate, run count, mean cost, mean grounding rates
 *   - MethodComparisonChart — Recharts BarChart with 3 grouped bars × 5 metrics
 *   - RunDetailTable        — paginated list of runs linking to /api/experiments/{id}/report
 *
 * Owner: Shahin
 * Requirements: 11.1–11.6, 12.1
 */

import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ExperimentRunSummary {
  id: string;
  baseline_method: "original_resume" | "generic_llm" | "proposed";
  original_score: number;
  final_score: number;
  decision_flipped: boolean;
  created_at: string;
}

interface PaginatedResult {
  items: ExperimentRunSummary[];
  total: number;
  page: number;
  page_size: number;
}

interface ExperimentFiltersState {
  baseline_method: string;
  start_date: string;
  end_date: string;
  threshold: string;
  model_name: string;
}

// ── API helpers ───────────────────────────────────────────────────────────────

const API_BASE = "/api";

async function fetchExperiments(
  filters: ExperimentFiltersState,
  page: number,
  page_size: number
): Promise<PaginatedResult> {
  const params = new URLSearchParams();
  if (filters.baseline_method) params.set("baseline_method", filters.baseline_method);
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  if (filters.threshold) params.set("threshold", filters.threshold);
  if (filters.model_name) params.set("model_name", filters.model_name);
  params.set("page", String(page));
  params.set("page_size", String(page_size));

  const res = await fetch(`${API_BASE}/experiments?${params.toString()}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? "Failed to fetch experiments");
  }
  const json = await res.json();
  return json.data as PaginatedResult;
}

// ── queryKeys factory (matches project convention from tasks.md) ──────────────

const queryKeys = {
  experiments: (filters: ExperimentFiltersState, page: number, pageSize: number) =>
    ["experiments", filters, page, pageSize] as const,
};

// ── ExperimentFilters ─────────────────────────────────────────────────────────

interface ExperimentFiltersProps {
  filters: ExperimentFiltersState;
  onChange: (next: ExperimentFiltersState) => void;
}

const ExperimentFilters: React.FC<ExperimentFiltersProps> = ({ filters, onChange }) => {
  const update = (key: keyof ExperimentFiltersState, value: string) =>
    onChange({ ...filters, [key]: value });

  return (
    <form
      aria-label="Experiment filters"
      style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", marginBottom: "1.5rem" }}
      onSubmit={(e) => e.preventDefault()}
      data-testid="experiment-filters"
    >
      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>Baseline method</span>
        <select
          value={filters.baseline_method}
          onChange={(e) => update("baseline_method", e.target.value)}
          aria-label="Baseline method filter"
          data-testid="filter-baseline-method"
        >
          <option value="">All</option>
          <option value="original_resume">Original resume</option>
          <option value="generic_llm">Generic LLM</option>
          <option value="proposed">Proposed</option>
        </select>
      </label>

      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>Start date</span>
        <input
          type="date"
          value={filters.start_date}
          onChange={(e) => update("start_date", e.target.value)}
          aria-label="Start date filter"
          data-testid="filter-start-date"
        />
      </label>

      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>End date</span>
        <input
          type="date"
          value={filters.end_date}
          onChange={(e) => update("end_date", e.target.value)}
          aria-label="End date filter"
          data-testid="filter-end-date"
        />
      </label>

      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>Threshold</span>
        <input
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={filters.threshold}
          onChange={(e) => update("threshold", e.target.value)}
          placeholder="e.g. 0.5"
          aria-label="Threshold filter"
          data-testid="filter-threshold"
          style={{ width: "80px" }}
        />
      </label>

      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>Model name</span>
        <input
          type="text"
          value={filters.model_name}
          onChange={(e) => update("model_name", e.target.value)}
          placeholder="e.g. all-MiniLM-L6-v2"
          aria-label="Model name filter"
          data-testid="filter-model-name"
          style={{ width: "180px" }}
        />
      </label>
    </form>
  );
};

// ── AggregateMetricsPanel ─────────────────────────────────────────────────────

interface AggregateMetricsPanelProps {
  items: ExperimentRunSummary[];
}

const AggregateMetricsPanel: React.FC<AggregateMetricsPanelProps> = ({ items }) => {
  const total = items.length;
  if (total === 0) {
    return (
      <div
        style={{ color: "#666", marginBottom: "1.5rem" }}
        data-testid="aggregate-panel-empty"
      >
        No experiment runs match the current filters.
      </div>
    );
  }

  const flipRate = items.filter((r) => r.decision_flipped).length / total;
  const meanScoreGain = items.reduce((acc, r) => acc + (r.final_score - r.original_score), 0) / total;

  const metrics: Array<{ label: string; value: string }> = [
    { label: "Runs", value: String(total) },
    { label: "Flip rate", value: `${(flipRate * 100).toFixed(1)}%` },
    { label: "Mean score gain", value: meanScoreGain.toFixed(3) },
  ];

  return (
    <div
      style={{ display: "flex", gap: "1.5rem", marginBottom: "1.5rem", flexWrap: "wrap" }}
      aria-label="Aggregate metrics"
      data-testid="aggregate-panel"
    >
      {metrics.map(({ label, value }) => (
        <div
          key={label}
          style={{
            background: "#f4f6f8",
            borderRadius: "6px",
            padding: "0.75rem 1.25rem",
            minWidth: "120px",
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "#666" }}>{label}</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{value}</div>
        </div>
      ))}
    </div>
  );
};

// ── MethodComparisonChart ─────────────────────────────────────────────────────

const BASELINE_LABELS: Record<string, string> = {
  original_resume: "Original",
  generic_llm: "Generic LLM",
  proposed: "Proposed",
};

const COLORS = {
  original_resume: "#6b7280",
  generic_llm: "#3b82f6",
  proposed: "#16a34a",
};

interface ChartDatum {
  metric: string;
  original_resume: number;
  generic_llm: number;
  proposed: number;
}

function buildChartData(items: ExperimentRunSummary[]): ChartDatum[] {
  // Group by baseline_method
  const groups: Record<string, ExperimentRunSummary[]> = {
    original_resume: [],
    generic_llm: [],
    proposed: [],
  };
  for (const item of items) {
    groups[item.baseline_method]?.push(item);
  }

  const avg = (arr: number[]) => (arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);

  const metrics = [
    {
      metric: "Flip rate",
      key: (g: ExperimentRunSummary[]) => avg(g.map((r) => (r.decision_flipped ? 1 : 0))),
    },
    {
      metric: "Avg original score",
      key: (g: ExperimentRunSummary[]) => avg(g.map((r) => r.original_score)),
    },
    {
      metric: "Avg final score",
      key: (g: ExperimentRunSummary[]) => avg(g.map((r) => r.final_score)),
    },
    {
      metric: "Avg score gain",
      key: (g: ExperimentRunSummary[]) => avg(g.map((r) => r.final_score - r.original_score)),
    },
    {
      metric: "Run count",
      key: (g: ExperimentRunSummary[]) => g.length,
    },
  ];

  return metrics.map(({ metric, key }) => ({
    metric,
    original_resume: parseFloat(key(groups.original_resume).toFixed(3)),
    generic_llm: parseFloat(key(groups.generic_llm).toFixed(3)),
    proposed: parseFloat(key(groups.proposed).toFixed(3)),
  }));
}

const MethodComparisonChart: React.FC<{ items: ExperimentRunSummary[] }> = ({ items }) => {
  const data = useMemo(() => buildChartData(items), [items]);

  if (items.length === 0) return null;

  return (
    <section
      aria-labelledby="chart-heading"
      style={{ marginBottom: "2rem" }}
      data-testid="method-comparison-chart"
    >
      <h2 id="chart-heading" style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>
        Method Comparison
      </h2>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="metric" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Legend />
          <Bar dataKey="original_resume" name={BASELINE_LABELS.original_resume} fill={COLORS.original_resume} />
          <Bar dataKey="generic_llm" name={BASELINE_LABELS.generic_llm} fill={COLORS.generic_llm} />
          <Bar dataKey="proposed" name={BASELINE_LABELS.proposed} fill={COLORS.proposed} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
};

// ── RunDetailTable ────────────────────────────────────────────────────────────

interface RunDetailTableProps {
  items: ExperimentRunSummary[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

const RunDetailTable: React.FC<RunDetailTableProps> = ({
  items,
  total,
  page,
  pageSize,
  onPageChange,
}) => {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <section aria-labelledby="table-heading" data-testid="run-detail-table">
      <h2 id="table-heading" style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>
        Run Details
      </h2>
      <div style={{ overflowX: "auto" }}>
        <table
          style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}
          aria-label="Experiment runs table"
        >
          <thead>
            <tr style={{ backgroundColor: "#f4f6f8" }}>
              <th style={thStyle}>ID</th>
              <th style={thStyle}>Method</th>
              <th style={thStyle}>Original score</th>
              <th style={thStyle}>Final score</th>
              <th style={thStyle}>Flipped?</th>
              <th style={thStyle}>Created</th>
              <th style={thStyle}>Report</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  style={{ textAlign: "center", padding: "1rem", color: "#666" }}
                  data-testid="empty-state"
                >
                  No experiment runs found for the current filters.
                </td>
              </tr>
            ) : (
              items.map((run) => (
                <tr key={run.id} style={{ borderBottom: "1px solid #e5e7eb" }}>
                  <td style={tdStyle} title={run.id}>
                    {run.id.substring(0, 8)}…
                  </td>
                  <td style={tdStyle}>{BASELINE_LABELS[run.baseline_method] ?? run.baseline_method}</td>
                  <td style={tdStyle}>{run.original_score.toFixed(3)}</td>
                  <td style={tdStyle}>{run.final_score.toFixed(3)}</td>
                  <td style={tdStyle}>{run.decision_flipped ? "✓" : "✗"}</td>
                  <td style={tdStyle}>{new Date(run.created_at).toLocaleDateString()}</td>
                  <td style={tdStyle}>
                    <a
                      href={`${API_BASE}/experiments/${run.id}/report`}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`View report for run ${run.id}`}
                      data-testid={`report-link-${run.id}`}
                    >
                      View report
                    </a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      <div
        style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", alignItems: "center" }}
        aria-label="Pagination"
      >
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          ←
        </button>
        <span>
          Page {page} of {totalPages}
        </span>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Next page"
        >
          →
        </button>
      </div>
    </section>
  );
};

const thStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  textAlign: "left",
  fontWeight: 600,
  borderBottom: "2px solid #e5e7eb",
};

const tdStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
};

// ── Main screen ───────────────────────────────────────────────────────────────

const ResearchEvaluationDashboardScreen: React.FC = () => {
  const [filters, setFilters] = useState<ExperimentFiltersState>({
    baseline_method: "",
    start_date: "",
    end_date: "",
    threshold: "",
    model_name: "",
  });
  const [page, setPage] = useState<number>(1);
  const PAGE_SIZE = 20;

  const query = useQuery<PaginatedResult, Error>({
    queryKey: queryKeys.experiments(filters, page, PAGE_SIZE),
    queryFn: () => fetchExperiments(filters, page, PAGE_SIZE),
    placeholderData: (prev) => prev,  // keep previous data while re-fetching
  });

  const handleFilterChange = (next: ExperimentFiltersState) => {
    setFilters(next);
    setPage(1); // Reset to page 1 on filter change
  };

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  return (
    <main
      style={{ padding: "1.5rem", maxWidth: "1200px", margin: "0 auto" }}
      aria-label="Research evaluation dashboard"
    >
      <h1 style={{ marginBottom: "0.25rem" }}>Research Evaluation Dashboard</h1>
      <p style={{ color: "#555", marginBottom: "1.5rem" }}>
        Comparative analysis of baseline methods across recorded experiment runs.
      </p>

      {/* Filters */}
      <ExperimentFilters filters={filters} onChange={handleFilterChange} />

      {/* Loading indicator */}
      {query.isLoading && (
        <div role="status" aria-live="polite" style={{ color: "#555", marginBottom: "1rem" }}>
          Loading experiments…
        </div>
      )}

      {/* Error banner */}
      {query.isError && (
        <div
          role="alert"
          style={{
            backgroundColor: "#fdecea",
            color: "#c0392b",
            padding: "1rem",
            borderRadius: "4px",
            marginBottom: "1rem",
          }}
          data-testid="error-banner"
        >
          {query.error.message}
        </div>
      )}

      {/* Aggregate metrics */}
      {!query.isLoading && !query.isError && (
        <AggregateMetricsPanel items={items} />
      )}

      {/* Method comparison chart */}
      {!query.isLoading && !query.isError && (
        <MethodComparisonChart items={items} />
      )}

      {/* Run detail table */}
      {!query.isLoading && !query.isError && (
        <RunDetailTable
          items={items}
          total={total}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
        />
      )}
    </main>
  );
};

export default ResearchEvaluationDashboardScreen;
