import { useNavigate } from 'react-router-dom'

function ElectionDetail() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="rounded-3xl bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-slate-600">Election Details</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Election Details</h1>

          <div className="mt-8 space-y-6 text-sm text-slate-700">
            <div>
              <p className="font-semibold text-slate-900">Election Title</p>
              <p>Student Council Election</p>
            </div>
            <div>
              <p className="font-semibold text-slate-900">Election Organizer</p>
              <p>Ms. Johnson</p>
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

export default ElectionDetail
