export const queryKeys = {
  resume: (id: string) => ['resume', id] as const,
  evidence: (candidateId: string) => ['evidence', candidateId] as const,
  analysis: (resumeVersionId: string) => ['analysis', resumeVersionId] as const,
  recourse: (resumeVersionId: string) => ['recourse', resumeVersionId] as const,
  experiments: () => ['experiments'] as const,
  experiment: (id: string) => ['experiments', id] as const,
}
