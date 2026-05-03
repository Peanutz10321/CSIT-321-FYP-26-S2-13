import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getElectionDetails, submitVote } from '../utils/api'

function CastVote() {
  const navigate = useNavigate()
  const location = useLocation()
  const [election, setElection] = useState(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const electionId = location.state?.electionId || new URLSearchParams(location.search).get('id')

  useEffect(() => {
    if (!electionId) {
      alert('No election selected.')
      navigate('/active-elections')
      return
    }

    getElectionDetails(electionId)
      .then((data) => {
        setElection(data)
        if (data.candidates?.length) {
          setSelectedCandidateId(data.candidates[0].id)
        }
      })
      .catch((error) => {
        alert(`Unable to load election: ${error.message}`)
        navigate('/active-elections')
      })
      .finally(() => setLoading(false))
  }, [electionId, navigate])

  const handleVote = async () => {
    if (!selectedCandidateId) {
      alert('Please select a candidate before submitting your vote.')
      return
    }

    setSubmitting(true)

    try {
      await submitVote({ election_id: electionId, candidate_id: selectedCandidateId })
      alert('Vote submitted successfully!')
      navigate('/vote-history')
    } catch (error) {
      alert(`Failed to submit vote: ${error.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 px-4 py-10">
        <div className="mx-auto max-w-4xl text-slate-700">Loading election details...</div>
      </div>
    )
  }

  if (!election) {
    return null
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Election Details</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">{election.title}</h1>
          <p className="mt-2 text-sm text-slate-600">Election ID: {election.id}</p>
        </div>

        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-900">Choose a Candidate</h2>
          <div className="mt-6 space-y-4">
            {election.candidates.map((candidate) => (
              <label
                key={candidate.id}
                className="flex cursor-pointer items-center justify-between rounded-3xl border border-slate-200 bg-slate-50 px-5 py-5 transition hover:border-blue-300"
              >
                <div>
                  <p className="text-base font-medium text-slate-900">{candidate.name}</p>
                </div>
                <input
                  type="radio"
                  name="candidate"
                  value={candidate.id}
                  checked={selectedCandidateId === candidate.id}
                  onChange={() => setSelectedCandidateId(candidate.id)}
                  className="h-5 w-5 text-blue-600"
                />
              </label>
            ))}
          </div>
        </div>

        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <button
            type="button"
            onClick={handleVote}
            disabled={submitting}
            className="w-full rounded-2xl bg-blue-600 px-5 py-4 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? 'Submitting Vote...' : 'Submit Vote'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default CastVote
