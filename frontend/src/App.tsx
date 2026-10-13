import { Routes, Route, Navigate } from 'react-router-dom'
import { SessionGuard } from './SessionGuard'
import { ResumeJDInputScreen } from './screens/ResumeJDInputScreen'
import { CandidateEvidenceReviewScreen } from './screens/CandidateEvidenceReviewScreen'
import { ATSAnalysisScreen } from './screens/ATSAnalysisScreen'
import { CounterfactualRecommendationsScreen } from './screens/CounterfactualRecommendationsScreen'
import { ComparisonScreen } from './screens/ComparisonScreen'
import { ResearchDashboard } from './screens/ResearchDashboard'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/input" replace />} />
      <Route path="/input" element={<ResumeJDInputScreen />} />
      <Route
        path="/evidence"
        element={
          <SessionGuard>
            <CandidateEvidenceReviewScreen />
          </SessionGuard>
        }
      />
      <Route
        path="/analysis"
        element={
          <SessionGuard>
            <ATSAnalysisScreen />
          </SessionGuard>
        }
      />
      <Route
        path="/recommendations"
        element={
          <SessionGuard>
            <CounterfactualRecommendationsScreen />
          </SessionGuard>
        }
      />
      <Route path="/comparison" element={<ComparisonScreen />} />
      <Route path="/research" element={<ResearchDashboard />} />
    </Routes>
  )
}
