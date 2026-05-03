import { useNavigate } from 'react-router-dom'

const candidates = [
  { name: 'Candidate A', votes: 150 },
  { name: 'Candidate B', votes: 120 },
  { name: 'Candidate C', votes: 90 },
]

function ElectionResults() {
  const navigate = useNavigate()
  const totalVotes = candidates.reduce((sum, candidate) => sum + candidate.votes, 0)

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-600">Election Results</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election Results</h1>

          <div className="mt-8 space-y-6 text-sm text-slate-700">
            <div>
              <p className="font-semibold text-slate-900">Election Title</p>
              <p>Student Council Election</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">List of Candidates</p>
              <ul className="mt-3 space-y-3">
                {candidates.map((candidate, index) => (
                  <li key={candidate.name} className="rounded-2xl bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-4">
                      <span className="font-medium text-slate-900">{candidate.name}</span>
                      <span className="text-slate-700">{candidate.votes} votes</span>
                    </div>
                    {index === 0 && <p className="mt-2 text-xs font-semibold uppercase text-emerald-700">Winner</p>}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Commence Date and Time</p>
              <p>12 Jun 2026, 09:00 AM</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">End Date and Time</p>
              <p>12 Jun 2026, 05:00 PM</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Total Votes Cast</p>
              <p>{totalVotes}</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Eligible Student Voters</p>
              <p>220</p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <button
            onClick={() => navigate('/election-history')}
            className="w-full rounded-2xl bg-blue-600 px-5 py-4 text-base font-semibold text-white transition hover:bg-blue-700"
          >
            Back to History
          </button>
        </div>
      </div>
    </div>
  )
}

export default ElectionResults
