# Requirements Document

## Introduction

This document specifies requirements for the **Verifiable Counterfactual Recourse for Resume–ATS Rejection** system — a research-oriented full-stack application that identifies the smallest truthful, evidence-supported changes a candidate can make to their resume to improve its chances of passing a simulated Applicant Tracking System (ATS) screening threshold.

The system's primary research contribution is demonstrating that *truth-constrained minimal-edit counterfactual recommendations* can achieve a comparable decision flip rate to generic LLM-generated suggestions while producing fewer unsupported claims and requiring smaller edits. The system explicitly operates on a **simulated** ATS model and does not claim to predict or reproduce any real employer's screening decision.

All recommendations are constrained to: rephrasing existing content, surfacing buried qualifications, reordering sections, normalizing terminology, reorganizing structure, and removing redundancy. The system must never fabricate skills, certifications, projects, responsibilities, or work experience.

---

## Glossary

- **ATS (Applicant Tracking System)**: A simulated scoring model used in this system to approximate resume screening. It is not a real employer ATS. Passing the simulated threshold does not guarantee an interview.
- **Candidate**: The user whose resume is being analyzed.
- **CandidateFact**: A discrete, sourced claim extracted from a candidate's documents (e.g., a skill, a project, a responsibility), stored in the Evidence Bank.
- **Claim**: A statement in the resume that asserts a skill, qualification, experience, achievement, or responsibility.
- **Counterfactual Edit**: A minimally-scoped change to a resume that is entirely grounded in existing candidate evidence and is expected to improve the simulated ATS score.
- **Decision Flip**: A change in the simulated ATS decision from "below threshold" to "at or above threshold" after applying recourse edits.
- **Edit Cost**: A composite metric in the range [0.0, 1.0] representing the total cost of all proposed edits, combining normalized textual edit distance, number of changed statements, degree of semantic change, and number of sections moved, each weighted equally at 0.25 by default.
- **Evidence Bank**: The canonical, structured collection of all CandidateFacts extracted from a candidate's uploaded documents.
- **Evidence Grounding**: The property that every substantive claim in the revised resume is traceable to at least one CandidateFact with a recorded source span.
- **ExperimentRun**: A logged, reproducible record of a single recourse generation session including model configuration, scores, edits, verification decisions, and metrics.
- **Grounding Rate**: The proportion of claims in the revised resume that are traceable to a CandidateFact with verification status `Supported` or `Partially Supported`.
- **JobRequirement**: A structured record of a requirement extracted from a job description, categorized as required or preferred.
- **Minimality**: The property that no edit in the accepted recourse set can be removed while still satisfying the ATS threshold and all verification constraints.
- **ProposedEdit**: A single, atomic recourse operation (rephrase, surface, reorder, normalize, reorganize, remove redundancy) with full provenance.
- **Recourse**: The complete set of ProposedEdits recommended to the Candidate to cross the simulated ATS threshold.
- **ResumeDocument**: A structured representation of an uploaded or manually entered resume, including extracted text and source spans.
- **ResumeVersion**: A snapshot of a resume at a specific point in the workflow, with associated ATS score and decision.
- **Score Breakdown**: The structured decomposition of the simulated ATS score into skill overlap and semantic similarity components.
- **Sentence-BERT**: A sentence-level embedding model used for semantic similarity scoring between resume content and job description content.
- **Source Span**: The character-level location within a source document where a claim originates, represented as a `{start, end}` character offset pair.
- **Threshold**: The configurable simulated ATS score in the range [0.0, 1.0] above which a resume is considered to pass screening. Default value is 0.5.
- **Unsupported Claim**: A claim appearing in the revised resume that cannot be traced to any CandidateFact in the Evidence Bank.
- **Verification Status**: One of four states assigned to a CandidateFact or ProposedEdit: `Supported`, `Partially Supported`, `Unsupported`, `Needs Confirmation`.

---

## Requirements

---

### Requirement 1: Resume Document Ingestion

**User Story:** As a Candidate, I want to upload my resume in PDF or DOCX format, so that the system can extract and structure its content for analysis without me manually re-entering it.

#### Acceptance Criteria

1. WHEN a Candidate uploads a PDF or DOCX file, THE Ingestion_Service SHALL extract the full text of the document and store it as a ResumeDocument with the fields: `id`, `candidate_id`, `filename`, `document_type`, `extracted_text`, and `created_at`.
2. WHEN text is extracted from a document, THE Ingestion_Service SHALL preserve character-level source spans (represented as `{start, end}` character offsets) for each extracted text segment so that downstream components can trace claims back to their origin location.
3. WHEN the uploaded file is a DOCX, THE Ingestion_Service SHALL use `python-docx` for text extraction.
4. WHEN the uploaded file is a PDF with selectable text, THE Ingestion_Service SHALL use `PyMuPDF` for text extraction.
5. IF a PDF contains no selectable text layer (i.e., character count extracted by PyMuPDF is zero), THEN THE Ingestion_Service SHALL apply OCR processing to extract text content.
6. IF the uploaded file exceeds 10 MB, THEN THE Ingestion_Service SHALL return an HTTP 413 error response without creating a ResumeDocument record.
7. IF the uploaded file format is neither PDF nor DOCX, THEN THE Ingestion_Service SHALL return an HTTP 415 error response indicating the unsupported file type without creating a ResumeDocument record.
8. IF text extraction produces an empty or blank result (zero non-whitespace characters), THEN THE Ingestion_Service SHALL return a structured error response describing the failure without creating a partial ResumeDocument record.
9. IF text extraction fails for any other reason, THEN THE Ingestion_Service SHALL return a structured error response containing a machine-readable `code` string and a human-readable `message` string, without creating a partial ResumeDocument record.
10. WHEN a Candidate submits manual text input of between 1 and 50,000 characters via `POST /api/resumes/manual`, THE Ingestion_Service SHALL store the text as a ResumeDocument with `document_type` set to `manual`.
11. IF manual text input exceeds 50,000 characters or is empty, THEN THE Ingestion_Service SHALL return an HTTP 422 error response without creating a ResumeDocument record.
12. WHEN a ResumeDocument is successfully created, THE Ingestion_Service SHALL expose the extracted resume content via `GET /api/resumes/{id}`.

---

### Requirement 2: Job Description Analysis

**User Story:** As a Candidate, I want to provide a job description so that the system can extract structured requirements and compare them against my resume.

#### Acceptance Criteria

1. WHEN a job description of between 1 and 10,000 characters is submitted via `POST /api/job-descriptions`, THE JD_Analyzer SHALL extract and store JobRequirement records covering: required skills, preferred skills, responsibilities, qualifications, experience requirements, and certifications.
2. IF the submitted job description body is empty or consists solely of whitespace, THEN THE JD_Analyzer SHALL return an HTTP 422 error response without creating a job description record.
3. THE JD_Analyzer SHALL assign each JobRequirement one of two `importance` values: `required` or `preferred`, based on signal words present in the source text (e.g., "must have", "required", "preferred", "nice to have"). WHEN no signal words are present for a JobRequirement, THE JD_Analyzer SHALL assign `importance = "required"` as the default.
4. THE JD_Analyzer SHALL preserve the `source_span` (as a `{start, end}` character offset pair) for each JobRequirement so the extracted requirement can be traced back to the original job description text.
5. THE JD_Analyzer SHALL distinguish between `explicit` requirements — those stated directly in the job description — and `inferred` requirements — those derived by the analyzer — and store this distinction in each JobRequirement record.
6. THE JD_Analyzer SHALL normalize skill names in each JobRequirement to a canonical form (e.g., "JS" → "JavaScript") and store the normalized form in the `normalized_skills` field. IF no canonical mapping exists for a skill name, THE JD_Analyzer SHALL preserve the original skill name in `normalized_skills`.
7. IF a job description is submitted that contains no extractable requirements, THEN THE JD_Analyzer SHALL return a response containing both the created job description record and a top-level `warning` field with a message indicating zero requirements were extracted.
8. WHEN a job description record is successfully created, THE JD_Analyzer SHALL expose extracted requirements via `GET /api/job-descriptions/{id}`.

---

### Requirement 3: Candidate Evidence Bank

**User Story:** As a Candidate, I want a structured, reviewable collection of all facts extracted from my resume, so that I can confirm, correct, or flag individual claims before the system uses them as evidence for recommendations.

#### Acceptance Criteria

1. WHEN a ResumeDocument is successfully ingested, THE Evidence_Extractor SHALL automatically create CandidateFact records by extracting discrete claims of the following types: `skill`, `project`, `responsibility`, `certification`, `experience`, `achievement`.
2. THE Evidence_Extractor SHALL assign each CandidateFact the fields: `id`, `candidate_id`, `claim_text`, `claim_type` (one of the six values above), `source_document_id`, `source_span` (as a `{start, end}` character offset pair), `verification_status`, `original_claim_text`, and `metadata`.
3. THE Evidence_Extractor SHALL set `verification_status = "Needs Confirmation"` on all CandidateFacts extracted automatically from a resume, and SHALL set `verification_status = "Supported"` only when additional corroborating documentation (e.g., a certificate or transcript) is provided and linked to the fact.
4. THE Evidence_Bank SHALL link each CandidateFact to related skills, projects, and experience entries via the `metadata` field or explicit association records, enabling downstream retrieval of related facts.
5. WHEN a Candidate requests their evidence bank via `GET /api/candidates/{id}/evidence`, THE Evidence_Bank SHALL return all CandidateFacts for that candidate including both `original_claim_text` and the current `claim_text` so the Candidate can see what (if anything) has been modified.
6. WHEN a Candidate submits a PATCH request to `PATCH /api/candidates/{id}/evidence/{fact_id}` with a valid `verification_status` value (one of `Supported`, `Partially Supported`, `Unsupported`, `Needs Confirmation`) and/or a non-empty `claim_text` string of up to 2,000 characters, THE Evidence_Bank SHALL update the specified fields and record the modification timestamp in `updated_at`.
7. IF a PATCH request contains an invalid `verification_status` value or a `claim_text` exceeding 2,000 characters or an empty `claim_text` string, THEN THE Evidence_Bank SHALL return an HTTP 422 error response without modifying the CandidateFact.
8. IF a Candidate sets `verification_status = "Unsupported"` on a CandidateFact, THEN THE Recourse_Engine SHALL exclude that fact from the set of usable evidence when generating ProposedEdits.
9. THE Evidence_Bank SHALL retain the `original_claim_text` field unchanged for the lifetime of the CandidateFact regardless of subsequent Candidate modifications, to preserve the audit trail.

---

### Requirement 4: Simulated ATS Scoring

**User Story:** As a Candidate, I want to see a structured simulated ATS score for my resume against a job description, so that I understand the baseline gap before any recourse is applied.

#### Acceptance Criteria

1. WHEN a scoring request is submitted via `POST /api/analysis` with a valid `resume_id` and `job_description_id`, THE ATS_Scorer SHALL compute a normalized score in the range [0.0, 1.0] composed of: (a) skill overlap between resume skills and JobRequirement normalized skills, and (b) Sentence-BERT semantic similarity between resume text and job description text.
2. THE ATS_Scorer SHALL apply configurable weights to the skill overlap and semantic similarity components. Each weight SHALL be a value in [0.0, 1.0] and the two weights SHALL sum to 1.0. The default configuration SHALL specify equal weighting of 0.5 for each component.
3. THE ATS_Scorer SHALL accept a configurable `threshold` value in the range [0.0, 1.0] with a default of 0.5. THE ATS_Scorer SHALL compare the computed score against the configured `threshold` value and record the binary `decision` as `pass` if the score is greater than or equal to the threshold, or `fail` otherwise.
4. THE ATS_Scorer SHALL produce a structured Score Breakdown containing: the total score, the skill overlap sub-score, the semantic similarity sub-score, the weights applied, and the threshold used.
5. THE ATS_Scorer SHALL be deterministic: given the same resume text, job description text, model version, weights, and threshold, THE ATS_Scorer SHALL always produce the same score and decision.
6. WHEN a scoring request completes successfully, THE ATS_Scorer SHALL store the result as a ResumeVersion record with fields: `id`, `original_resume_id`, `version_number`, `content`, `ats_score`, `decision`, and `created_at`. The `version_number` SHALL be set to 1 for the baseline scoring result and SHALL be incremented by 1 relative to the highest existing `version_number` for that `original_resume_id` for each subsequent version.
7. IF a scoring request references a `resume_id` or `job_description_id` that does not exist, THE ATS_Scorer SHALL return an HTTP 404 error response without creating a ResumeVersion record.
8. IF the Sentence-BERT model fails to produce an embedding, THE ATS_Scorer SHALL return a structured error response with a machine-readable `code` and a human-readable `message`, without creating a ResumeVersion record.
9. THE System SHALL display a disclosure to the Candidate stating that the ATS score is produced by a simulated model and that passing the threshold does not guarantee an interview with any employer.

---

### Requirement 5: Counterfactual Edit Generation

**User Story:** As a Candidate, I want the system to propose specific, evidence-backed edits to my resume, so that I receive actionable recommendations that improve my simulated ATS score without inventing qualifications I do not have.

#### Acceptance Criteria

1. WHEN a recourse request is submitted via `POST /api/recourse/generate` with a valid `resume_version_id` and `job_description_id`, THE Recourse_Engine SHALL generate ProposedEdits using only the following edit operation types: `rephrase`, `surface_qualification`, `reorder`, `normalize_terminology`, `reorganize_sections`, `remove_redundancy`.
2. THE Recourse_Engine SHALL constrain every ProposedEdit to operations that are grounded in at least one CandidateFact with `verification_status` of `Supported`, `Partially Supported`, or `Needs Confirmation`. THE Recourse_Engine SHALL NOT generate edits grounded solely in CandidateFacts with `verification_status = "Unsupported"`.
3. THE Recourse_Engine SHALL never generate a ProposedEdit that introduces a skill, qualification, certification, project, responsibility, or work experience that is not present in the Candidate's Evidence Bank.
4. WHEN generating a `rephrase` edit, THE Recourse_Engine SHALL retain the original semantic meaning of the claim as measured by Sentence-BERT cosine similarity, and SHALL NOT produce a rephrase edit with a similarity score below 0.85 between `original_text` and `proposed_text`.
5. THE Recourse_Engine SHALL record for each ProposedEdit: `id`, `resume_version_id`, `original_text`, `proposed_text`, `edit_type`, `evidence_fact_ids` (list of CandidateFact IDs), `job_requirement_ids` (list of JobRequirement IDs addressed), `verification_status` (set to `Needs Confirmation` at generation time), `edit_cost`, and `score_contribution`.
6. THE Recourse_Engine SHALL associate each ProposedEdit with the specific JobRequirement records it is intended to address. IF a ProposedEdit cannot be associated with at least one JobRequirement, THE Recourse_Engine SHALL not generate that edit.
7. THE Recourse_Engine SHALL generate no more than 20 ProposedEdits per recourse request.
8. IF no ProposedEdits can be generated that satisfy all constraints, THEN THE Recourse_Engine SHALL return an `infeasible` response containing a machine-readable `reason` field (one of: `no_evidence`, `all_unsupported`, `no_requirement_match`) and a human-readable `detail` string, without fabricating edits.

---

### Requirement 6: Minimal-Edit Optimization

**User Story:** As a Candidate and as a researcher, I want the system to find the smallest set of valid edits that crosses the simulated ATS threshold, so that recommendations are precise, non-redundant, and meaningful for research comparison.

#### Acceptance Criteria

1. WHEN ProposedEdits have been generated, THE Optimizer SHALL select the subset of edits with minimum total Edit Cost that: (a) causes the simulated ATS score to meet or exceed the configured threshold, (b) maintains all claims as `Supported` or `Partially Supported`, (c) introduces no `Unsupported` skills, and (d) preserves all CandidateFacts present in the original ResumeDocument's Evidence Bank.
2. THE Optimizer SHALL compute Edit Cost for each ProposedEdit as a composite score in the range [0.0, 1.0] using four equally-weighted sub-components (each weighted 0.25): (a) normalized Levenshtein distance between `original_text` and `proposed_text` (normalized by the length of the longer string), (b) number of changed statements divided by total statements in the original resume, (c) degree of semantic change (1 minus Sentence-BERT cosine similarity between `original_text` and `proposed_text`), and (d) number of sections moved divided by total sections in the original resume. These weights are configurable per ExperimentRun.
3. WHEN the Optimizer applies the selected edit set to the original resume, THE Optimizer SHALL verify that: (a) all named sections present in the original resume remain present in the revised resume, (b) the contact block (name, email, phone) is unchanged, and (c) every CandidateFact in the Evidence Bank is represented in the revised resume text.
4. IF no feasible subset of edits exists that meets all constraints and crosses the threshold, THEN THE Optimizer SHALL return a response with `status = "infeasible"` and a `constraints_violated` field listing which constraint(s) (threshold, support, fabrication, fact_preservation) prevented a solution.
5. WHEN the result is `infeasible`, THE Optimizer SHALL also return a `partial_result` field containing the lowest-cost edit subset found during the search, along with its total Edit Cost and projected ATS score, so the researcher can inspect partial progress.
6. WHEN the Optimizer selects a feasible recourse set, THE Optimizer SHALL report the total Edit Cost of the accepted set, the projected final ATS score, and the projected decision (`pass` or `fail`).
7. THE Optimizer SHALL never relax the constraint against fabrication to achieve threshold crossing. IF the only path to threshold crossing requires introducing an `Unsupported` claim, THE Optimizer SHALL return an `infeasible` result.

---

### Requirement 7: Evidence Verification

**User Story:** As a researcher, I want every claim in the generated recourse to be verified against source evidence before being presented to the Candidate, so that recommendation quality can be objectively measured.

#### Acceptance Criteria

1. WHEN a recourse set is submitted for verification via `POST /api/recourse/{id}/verify`, THE Verifier SHALL check each ProposedEdit by performing: (a) direct source-span matching between the proposed claim and the referenced CandidateFact's `source_span`, (b) structured comparison of entities, skills, and facts between the proposed text and the evidence, and (c) entity and skill consistency checking to detect additions not present in the evidence.
2. WHEN verification is performed on a ProposedEdit, THE Verifier SHALL apply semantic entailment analysis to determine whether the proposed text is entailed by the referenced CandidateFact. THE Verifier SHALL record the normalized entailment score (in the range [0.0, 1.0]) as part of the verification output. A score of 0.5 or above SHALL be treated as entailed.
3. WHEN an LLM is used to assist verification, THE Verifier SHALL record the LLM's output as advisory evidence only. THE Verifier SHALL NOT set `verification_status = "Supported"` or `verification_status = "Partially Supported"` based solely on LLM confidence. LLM advisory output MAY only elevate a status from `Unsupported` to `Needs Confirmation`.
4. WHEN verification is complete for a ProposedEdit, THE Verifier SHALL assign one Verification Status value using the following ordered decision rules: (a) IF source-span match is found AND entailment score ≥ 0.5 AND no new entity or skill is detected, THEN `Supported`; (b) IF source-span match is found AND (entailment score < 0.5 OR a minor related entity is detected), THEN `Partially Supported`; (c) IF no source-span match is found AND entailment score ≥ 0.5 AND no new entity or skill is detected, THEN `Needs Confirmation`; (d) IF a new entity or skill not present in any referenced CandidateFact is detected, THEN `Unsupported` regardless of other signals.
5. WHEN a ProposedEdit receives `verification_status = "Needs Confirmation"`, THE System SHALL surface the edit to the Candidate for manual review before including it in the accepted recourse set.
6. WHEN a ProposedEdit receives `verification_status = "Unsupported"`, THE Recourse_Engine SHALL exclude that edit from the accepted recourse set and recalculate the optimization under the reduced edit set. IF recalculation yields an infeasible result, THE System SHALL return an `infeasible` response as specified in Requirement 6.
7. THE Verifier SHALL produce a structured verification report per edit containing: the verification method(s) used (one or more of: `source_span_match`, `entity_check`, `entailment`, `llm_advisory`), the IDs of CandidateFact evidence references consulted, the assigned status, and a rationale string that identifies which evidence supported or contradicted the claim.
8. THE Verifier SHALL always assign a status for every ProposedEdit submitted, regardless of the completeness of the evidence combination process.

---

### Requirement 8: Recourse Explanation

**User Story:** As a Candidate, I want a clear explanation for each recommended edit, so that I understand what changed, why the change was suggested, and what evidence supports it.

#### Acceptance Criteria

1. WHEN a recourse set has been verified and accepted edits are available, THE Explanation_Service SHALL generate a structured explanation for each accepted ProposedEdit containing: (a) a prose description (plain text or structured text) of what text changed, (b) the reason the change is expected to improve the simulated ATS score, (c) the IDs and `claim_text` of the specific CandidateFact(s) from the Evidence Bank that provide grounding, (d) the IDs and `requirement_text` of the JobRequirement(s) the edit addresses, (e) the `score_contribution` value, (f) the `edit_cost` value, and (g) the `verification_status`.
2. WHEN the Counterfactual Recommendations screen is loaded, THE Explanation_Service SHALL render one explanation card per accepted ProposedEdit, with each card presenting all seven fields from criterion 1.
3. WHEN individual edit explanations have been generated and at least one explanation card is rendered, THE Explanation_Service SHALL display the following aggregate recourse metrics alongside those explanations: total edit cost, projected final score, projected decision, overall grounding rate, and unsupported-claim rate.
4. IF a ProposedEdit has `verification_status = "Needs Confirmation"`, THE Explanation_Service SHALL render that edit's card with a distinct label (e.g., "Needs Your Confirmation") and a visual indicator (e.g., a yellow border or badge) that distinguishes it from fully-supported edits, and SHALL present Confirm and Reject controls for the Candidate.
5. WHEN a Candidate confirms a `Needs Confirmation` edit, THE System SHALL set `verification_status = "Supported"` for that ProposedEdit and include it in the accepted recourse set.
6. WHEN a Candidate rejects a `Needs Confirmation` edit, THE System SHALL set `verification_status = "Unsupported"` for that ProposedEdit and exclude it from the accepted recourse set without triggering regeneration.

---

### Requirement 9: Resume Export

**User Story:** As a Candidate, I want to review the revised resume and export it after accepting recommendations, so that I have a safe, clean version to use in my job search without risk of losing my original.

#### Acceptance Criteria

1. WHEN a Candidate accepts a recourse set via `POST /api/recourse/{id}/accept`, THE Export_Service SHALL apply all accepted ProposedEdits to the original resume text and store the result as a new ResumeVersion record with `version_number` incremented by 1 relative to the highest existing `version_number` for that `original_resume_id`.
2. THE Export_Service SHALL preserve the original ResumeDocument and the baseline ResumeVersion (version_number = 1) without modification; the original SHALL NOT be silently overwritten.
3. WHEN a Candidate navigates to the Final Resume Comparison screen, THE Candidate_Review_UI SHALL present a side-by-side comparison showing the baseline ResumeVersion content on the left and the newly created ResumeVersion content on the right, before the Candidate confirms the export.
4. WHEN the Candidate confirms export, THE Export_Service SHALL make the revised resume available for download as a plain-text `.txt` file or a PDF file. At least one of these two formats SHALL be available on every export.
5. WHEN an export is confirmed and the revised ResumeVersion is stored, THE Export_Service SHALL record the accepted ResumeVersion's `id`, `ats_score`, and `decision` in the associated ExperimentRun record. IF no ExperimentRun exists for the session, THE Export_Service SHALL create one before recording these values.
6. IF export generation fails (e.g., file serialization error), THEN THE Export_Service SHALL return a structured error response containing a machine-readable `code` and a human-readable `message`, and SHALL NOT create a partial or corrupted ResumeVersion record.

---

### Requirement 10: Experiment Recording

**User Story:** As a researcher, I want every recourse session to be logged with full reproducibility metadata, so that results can be compared across methods, candidates, and model configurations.

#### Acceptance Criteria

1. WHEN a recourse session completes via `POST /api/recourse/{id}/accept` or returns an `infeasible` result, THE Experiment_Logger SHALL create an ExperimentRun record with the fields: `id`, `resume_id`, `job_description_id`, `model_configuration`, `baseline_method`, `original_score`, `final_score`, `threshold`, `decision_flipped`, `total_edit_cost`, `grounding_metrics`, `random_seed`, and `created_at`. For infeasible runs, `final_score` SHALL be set to the projected score of the partial result, `decision_flipped` SHALL be `false`, and `total_edit_cost` SHALL reflect the partial edit set cost.
2. WHEN an ExperimentRun record is created, THE Experiment_Logger SHALL record the `model_configuration` as a JSON object capturing: Sentence-BERT model name and version, spaCy model name and version, ATS scoring weights, threshold value, and optimization hyperparameters (including Edit Cost component weights).
3. WHEN an ExperimentRun record is created, THE Experiment_Logger SHALL record the `random_seed` integer used in any stochastic component (e.g., LLM sampling) so that the run is reproducible. If no stochastic component was used, `random_seed` SHALL be recorded as `null`.
4. WHEN an ExperimentRun record is created, THE Experiment_Logger SHALL record all generated ProposedEdits (including those rejected during verification or optimization) and their individual verification decisions, not only the final accepted set.
5. WHEN an ExperimentRun record is created, THE grounding_metrics field SHALL contain a JSON object with three keys: `evidence_grounding_rate` (proportion of accepted edits with status `Supported` or `Partially Supported`), `unsupported_claim_rate` (proportion of all generated edits with final status `Unsupported`), and `original_fact_preservation_rate` (proportion of original CandidateFacts present in the revised resume).
6. WHEN an ExperimentRun record is created, THE Experiment_Logger SHALL record `baseline_method` as one of: `original_resume` (Baseline A), `generic_llm` (Baseline B), or `proposed` (the verifiable minimal recourse method). IF a value outside these three is submitted, THE Experiment_Logger SHALL return an HTTP 422 error response.
7. WHEN an ExperimentRun record is successfully created, THE Experiment_Logger SHALL expose the record via `GET /api/experiments/{id}` and a structured report via `GET /api/experiments/{id}/report`.
8. THE Experiment_Logger SHALL create ExperimentRun records as append-only entries; existing ExperimentRun records SHALL NOT be modified after creation.

---

### Requirement 11: Research Evaluation Dashboard

**User Story:** As a researcher, I want a dedicated dashboard that visualizes the primary research metrics across multiple experiment runs, so that I can compare the proposed method against baselines and assess the primary hypothesis.

#### Acceptance Criteria

1. WHEN the Research Evaluation Dashboard is loaded, THE Research_Dashboard SHALL display aggregate metrics computed across all ExperimentRuns returned by `GET /api/experiments`, including: flip rate (count of `decision_flipped = true` / total run count), total run count, mean edit cost, mean evidence grounding rate, mean unsupported-claim rate, and mean original-fact preservation rate.
2. THE Research_Dashboard SHALL support filtering ExperimentRuns by `baseline_method` (one of the three valid values), date range (ISO 8601 start date and end date), threshold value, and model name (matched against the `model_configuration.sbert_model` field). WHEN multiple filters are applied simultaneously, THE Research_Dashboard SHALL combine them with AND logic, returning only ExperimentRuns that satisfy all active filter conditions. WHEN no ExperimentRuns match the active filters, THE Research_Dashboard SHALL display a zero-results message rather than an error.
3. WHEN the Research Evaluation Dashboard is loaded, THE Research_Dashboard SHALL render grouped bar charts (using Recharts) contrasting ExperimentRuns with `baseline_method = "proposed"` against `baseline_method = "original_resume"` and `baseline_method = "generic_llm"` on each primary metric: flip rate, mean edit cost, mean grounding rate, mean unsupported-claim rate, and mean fact-preservation rate.
4. THE Research_Dashboard SHALL display a list of per-run detail records, each linking to the `GET /api/experiments/{id}/report` URL for that ExperimentRun.
5. THE Research_Dashboard SHALL be accessible via the fixed frontend route `/research`.
6. THE API SHALL expose `GET /api/experiments` returning a paginated list of ExperimentRun summary records (id, baseline_method, original_score, final_score, decision_flipped, created_at) to support dashboard data loading.

---

### Requirement 12: Frontend Screens and Navigation

**User Story:** As a Candidate and as a researcher, I want a coherent multi-screen application that guides me through the full recourse workflow, so that each step of the process is clear and actionable.

#### Acceptance Criteria

1. THE Frontend SHALL provide the following named screens, each accessible via a distinct route managed by React Router: Dashboard (`/`), Resume & JD Input (`/input`), Candidate Evidence Review (`/evidence`), ATS Analysis (`/analysis`), Counterfactual Recommendations (`/recommendations`), Final Resume Comparison (`/comparison`), and Research Evaluation Dashboard (`/research`).
2. WHEN the Dashboard screen is loaded, THE Dashboard SHALL display: up to 5 active sessions (sessions with a ResumeDocument and no completed export) sorted by most recently updated, up to 10 recent ExperimentRun summaries sorted by `created_at` descending, and navigation links to all major screens.
3. WHEN a Candidate submits the Resume & JD Input form, THE Resume_JD_Input_Screen SHALL accept either a PDF or DOCX file upload (max 10 MB) or manual resume text (max 50,000 characters), and a job description text input (max 10,000 characters), and SHALL display a loading indicator while the submission is processed.
4. WHEN the Candidate Evidence Review screen is loaded, THE Candidate_Evidence_Review_Screen SHALL display all CandidateFacts for the active session with their `claim_text`, `claim_type`, `verification_status`, and the `original_claim_text` for comparison. The Candidate SHALL be able to update `claim_text` and `verification_status` for individual facts before recourse is generated.
5. THE ATS_Analysis_Screen SHALL display the Score Breakdown for the baseline resume, including total score, sub-scores, weights, and threshold, alongside the ATS disclosure statement.
6. THE Counterfactual_Recommendations_Screen SHALL display each ProposedEdit with its explanation card and SHALL allow the Candidate to accept or reject individual edits before finalizing recourse. WHEN a Candidate rejects a ProposedEdit, THE System SHALL exclude that edit from the accepted recourse set without triggering regeneration of new alternative edits.
7. WHEN the Final Resume Comparison screen is loaded, THE Final_Resume_Comparison_Screen SHALL present a side-by-side diff view of the original and revised resume with additions highlighted and deletions struck through at sentence-level granularity, and SHALL provide a download control for plain-text `.txt` or PDF export.
8. THE Frontend SHALL use TanStack Query for all API data fetching, caching, and invalidation. WHEN an API request is in-flight, THE Frontend SHALL display a loading indicator. WHEN an API request fails, THE Frontend SHALL display an error message with a retry option.
9. WHEN a Candidate navigates directly to `/evidence`, `/analysis`, `/recommendations`, or `/comparison` without an active session, THE Frontend SHALL redirect the Candidate to `/input` with a message indicating that a resume and job description must be provided first.

---

### Requirement 13: API Design and Correctness

**User Story:** As a developer and integrator, I want the backend API to be well-structured, validated, and consistent, so that all frontend and research tooling can integrate reliably.

#### Acceptance Criteria

1. THE API SHALL expose the following endpoints: `POST /api/resumes/upload`, `POST /api/resumes/manual`, `GET /api/resumes/{id}`, `POST /api/job-descriptions`, `GET /api/job-descriptions/{id}`, `GET /api/candidates/{id}/evidence`, `PATCH /api/candidates/{id}/evidence/{fact_id}`, `POST /api/analysis`, `POST /api/recourse/generate`, `POST /api/recourse/{id}/verify`, `POST /api/recourse/{id}/accept`, `POST /api/experiments`, `GET /api/experiments`, `GET /api/experiments/{id}`, and `GET /api/experiments/{id}/report`.
2. THE API SHALL validate all request bodies using Pydantic models. WHEN a request body fails schema validation, THE API SHALL return HTTP 422 with an error envelope containing a top-level `error` field with at minimum a machine-readable `code` string and a human-readable `message` string.
3. WHEN a resource referenced by a path parameter does not exist, THE API SHALL return HTTP 404 with an error envelope containing a top-level `error` field with at minimum a machine-readable `code` string and a human-readable `message` string.
4. WHEN a request attempts to create a resource that violates a uniqueness constraint, THE API SHALL return HTTP 409 with an error envelope containing a top-level `error` field with at minimum a machine-readable `code` string and a human-readable `message` string.
5. THE API SHALL use consistent JSON response envelopes across all endpoints: successful responses SHALL contain a top-level `data` field and SHALL NOT contain a top-level `error` field; error responses SHALL contain a top-level `error` field and SHALL NOT contain a top-level `data` field. Pagination metadata (e.g., `total`, `page`, `page_size`) SHALL be nested inside `data` where applicable.
6. THE API SHALL be implemented in Python using FastAPI with SQLAlchemy for database access and Alembic for schema migrations.

---

### Requirement 14: Data Persistence and Integrity

**User Story:** As a researcher, I want all data to be persisted reliably in PostgreSQL with referential integrity, so that experiment records, resume versions, and evidence facts are never silently lost or corrupted.

#### Acceptance Criteria

1. THE Database SHALL store all domain model records — ResumeDocument, CandidateFact, JobRequirement, ResumeVersion, ProposedEdit, ExperimentRun — in PostgreSQL with foreign key constraints enforcing referential integrity between all related entities.
2. THE Database SHALL use Alembic migrations to manage all schema changes; direct schema modifications outside the migration system (e.g., manual `ALTER TABLE` statements) SHALL NOT be applied to the database.
3. THE Database SHALL enforce that a ProposedEdit record cannot be created without a valid `resume_version_id` referencing an existing ResumeVersion.
4. THE Database SHALL enforce that a CandidateFact record cannot be created without a valid `source_document_id` referencing an existing ResumeDocument.
5. THE Database SHALL enforce that an ExperimentRun record cannot be created without valid `resume_id` and `job_description_id` references pointing to existing records.
6. WHEN a ResumeDocument is deleted, THE Database SHALL cascade the deletion to all associated CandidateFact records belonging to that document.
7. THE Database SHALL store all `verification_status` fields as enumerated types restricted to the four valid values: `Supported`, `Partially Supported`, `Unsupported`, `Needs Confirmation`. Any attempt to insert an out-of-range value SHALL be rejected at the database constraint level.

---

### Requirement 15: Team Collaboration and Git Workflow

**User Story:** As a team member, I want a defined branch strategy, PR workflow, and definition of done, so that all six contributors can work in parallel without conflicts and Varun can integrate changes safely.

#### Acceptance Criteria

1. THE Repository SHALL maintain a protected `main` branch and a long-lived `integration` branch. Only Varun SHALL merge pull requests into `main`. All feature branches SHALL target `integration`.
2. THE Repository SHALL enforce the following branch naming convention per teammate and module domain:
   - `varun/<task-slug>` — core research mechanism, recourse engine, optimizer, and final integration (e.g., `varun/recourse-engine`, `varun/optimizer`, `varun/integration-milestone-3`)
   - `vaishnavi/<task-slug>` — ATS scorer and evidence verification (e.g., `vaishnavi/ats-scorer`, `vaishnavi/evidence-verification`)
   - `vipul/<task-slug>` — resume ingestion and experiment logger (e.g., `vipul/resume-ingestion`, `vipul/experiment-logger`)
   - `dhruv/<task-slug>` — JD analyzer and evidence bank (e.g., `dhruv/jd-analyzer`, `dhruv/evidence-bank`)
   - `yash/<task-slug>` — frontend screens and API integration tests (e.g., `yash/frontend-screens`, `yash/api-tests`)
   - `shahin/<task-slug>` — research dashboard, export service, and end-to-end tests (e.g., `shahin/research-dashboard`, `shahin/export-service`)
3. WHEN a teammate opens a pull request targeting `integration`, THE PR description SHALL include: (a) a summary of changes, (b) a link to the relevant task ID from tasks.md, (c) a list of tests run and their pass/fail status, and (d) identification of any downstream modules that depend on this change.
4. WHEN a pull request targeting `integration` is ready to merge, THE PR_Workflow SHALL require: (a) at least one approving review from a teammate other than the author, and (b) a final review and merge action performed by Varun. No teammate other than Varun SHALL perform the merge into `integration`.
5. THE Definition_of_Done for a task SHALL require all five of the following conditions to be met: (a) all acceptance criteria for the task are implemented and verified, (b) all unit tests for the task pass locally, (c) the branch has been rebased on the latest `integration` branch with no conflicts, (d) the PR description is complete per criterion 3, and (e) CI checks (lint, type check, tests) pass on the PR.
6. THE Repository SHALL document a dependency graph in the project README identifying the integration order: (1) database schema and shared models, (2) resume ingestion and evidence extraction, (3) JD analysis and ATS scoring, (4) recourse generation and optimization, (5) evidence verification and recourse explanation, (6) resume export and experiment logging, (7) frontend screens and research evaluation dashboard.
7. THE Repository SHALL track the following integration milestones, each gated on Varun's merge approval:
   - **Milestone 1**: Database schema + resume ingestion (Tasks owned by Varun and Vipul)
   - **Milestone 2**: ATS scoring + evidence bank + JD analysis (Tasks owned by Vaishnavi and Dhruv)
   - **Milestone 3**: Recourse generation + minimal-edit optimization (Tasks owned by Varun)
   - **Milestone 4**: Evidence verification + recourse explanation (Tasks owned by Vaishnavi)
   - **Milestone 5**: Frontend screens + resume export + research dashboard (Tasks owned by Yash and Shahin)
   - **Milestone 6**: Experiment logging + end-to-end integration + evaluation (Tasks owned by all, integrated by Varun)
