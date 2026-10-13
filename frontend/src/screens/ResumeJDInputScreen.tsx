import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { useSession } from '../session'
import { uploadResumeFile, submitManualResume } from '../api/resumes'
import { createJobDescription } from '../api/job_descriptions'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorBanner } from '../components/ErrorBanner'
import styles from './ResumeJDInputScreen.module.css'

const MAX_RESUME_CHARS = 50_000
const MAX_JD_CHARS = 10_000
const MAX_FILE_BYTES = 10 * 1024 * 1024

type Mode = 'upload' | 'text'

export function ResumeJDInputScreen() {
  const navigate = useNavigate()
  const { setSession, session } = useSession()

  const [mode, setMode] = useState<Mode>('upload')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [resumeText, setResumeText] = useState('')
  const [jdText, setJdText] = useState('')

  const resumeMutation = useMutation({
    mutationFn: async () => {
      const candidateId = session.candidateId ?? crypto.randomUUID()
      if (mode === 'upload') {
        if (!selectedFile) throw new Error('No file selected')
        return uploadResumeFile(selectedFile, candidateId)
      } else {
        return submitManualResume(resumeText, candidateId)
      }
    },
  })

  const jdMutation = useMutation({
    mutationFn: (text: string) => createJobDescription(text),
  })

  const isLoading = resumeMutation.isPending || jdMutation.isPending

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFileError(null)
    const file = e.target.files?.[0] ?? null
    if (file && file.size > MAX_FILE_BYTES) {
      setFileError('File size must not exceed 10 MB.')
      setSelectedFile(null)
      e.target.value = ''
      return
    }
    setSelectedFile(file)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    try {
      const resume = await resumeMutation.mutateAsync()
      const jd = await jdMutation.mutateAsync(jdText)
      setSession({
        resumeId: resume.id,
        candidateId: resume.candidate_id,
        jobDescriptionId: jd.id,
      })
      navigate('/evidence')
    } catch {
      // errors surfaced via mutation state
    }
  }

  const resumeError = resumeMutation.error as Error | null
  const jdError = jdMutation.error as Error | null

  return (
    <div className={styles.container}>
      <h1>Upload Your Resume</h1>

      <div className={styles.tabs}>
        <button
          type="button"
          className={`${styles.tab} ${mode === 'upload' ? styles.tabActive : ''}`}
          onClick={() => setMode('upload')}
        >
          Upload File
        </button>
        <button
          type="button"
          className={`${styles.tab} ${mode === 'text' ? styles.tabActive : ''}`}
          onClick={() => setMode('text')}
        >
          Enter Text
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        {mode === 'upload' ? (
          <div className={styles.field}>
            <label htmlFor="resume-file">Resume file (.pdf, .docx)</label>
            <input
              id="resume-file"
              type="file"
              accept=".pdf,.docx"
              onChange={handleFileChange}
            />
            {fileError && <ErrorBanner message={fileError} />}
          </div>
        ) : (
          <div className={styles.field}>
            <label htmlFor="resume-text">Resume Text</label>
            <textarea
              id="resume-text"
              rows={10}
              maxLength={MAX_RESUME_CHARS}
              value={resumeText}
              onChange={e => setResumeText(e.target.value)}
              placeholder="Paste your resume text here..."
            />
            <div className={styles.counter}>
              {resumeText.length} / {MAX_RESUME_CHARS.toLocaleString()}
            </div>
          </div>
        )}

        <div className={styles.field}>
          <label htmlFor="jd-text">Job Description</label>
          <textarea
            id="jd-text"
            rows={6}
            maxLength={MAX_JD_CHARS}
            value={jdText}
            onChange={e => setJdText(e.target.value)}
            placeholder="Paste the job description here..."
          />
          <div className={styles.counter}>
            {jdText.length} / {MAX_JD_CHARS.toLocaleString()}
          </div>
        </div>

        {resumeError && <ErrorBanner message={resumeError.message} />}
        {jdError && <ErrorBanner message={jdError.message} />}

        {isLoading && <LoadingSpinner />}

        <button type="submit" className={styles.submitBtn} disabled={isLoading}>
          Submit
        </button>
      </form>
    </div>
  )
}
