import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const candidates = ['Candidate 1', 'Candidate 2', 'Candidate 3']

function CastVote() {
  const [selectedCandidate, setSelectedCandidate] = useState('Candidate 1')
  const navigate = useNavigate()

  const handleVote = () => {
    alert('Vote submitted!')
    navigate('/vote-history')
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Election Details</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election Title</h1>
          <p className="mt-2 text-sm text-slate-600">School ID: SCH-00123</p>
        </div>

        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-900">Choose a Candidate</h2>
          <div className="mt-6 space-y-4">
            {candidates.map((candidate) => (
              <label
                key={candidate}
                className="flex cursor-pointer items-center justify-between rounded-3xl border border-slate-200 bg-slate-50 px-5 py-5 transition hover:border-blue-300"
              >
                <div>
                  <p className="text-base font-medium text-slate-900">{candidate}</p>
                </div>
                <input
                  type="radio"
                  name="candidate"
                  value={candidate}
                  checked={selectedCandidate === candidate}
                  onChange={() => setSelectedCandidate(candidate)}
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
            className="w-full rounded-2xl bg-blue-600 px-5 py-4 text-base font-semibold text-white transition hover:bg-blue-700"
          >
            {/* TODO: Implement Paillier Encryption here before submit */}
            Vote
          </button>
        </div>
      </div>
    </div>
  )
}

export default CastVote
