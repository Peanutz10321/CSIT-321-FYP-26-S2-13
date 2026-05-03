import { useNavigate } from 'react-router-dom'

function VoteReceipt() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-600">Vote Receipt</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election Title</h1>
          <div className="mt-6 space-y-5 text-sm text-slate-700">
            <div>
              <p className="font-semibold text-slate-900">School ID</p>
              <p>SCH-00123</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">List of Candidates</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">
                <li>Candidate 1</li>
                <li>Candidate 2</li>
                <li>Candidate 3</li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Election Commence Date and Time</p>
              <p>12 Jun 2026, 09:00 AM</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Election End Date and Time</p>
              <p>12 Jun 2026, 05:00 PM</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Date and Time Vote Casted</p>
              <p>12 Jun 2026, 10:23 AM</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Election Organizer</p>
              <p>School Election Committee</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Voted Candidate</p>
              <p>Candidate 2</p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <button
            onClick={() => navigate('/vote-history')}
            className="w-full rounded-2xl bg-blue-600 px-5 py-4 text-base font-semibold text-white transition hover:bg-blue-700"
          >
            Back to History
          </button>
        </div>
      </div>
    </div>
  )
}

export default VoteReceipt
