import { useNavigate } from 'react-router-dom'

function TeacherDashboard() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-col gap-4 rounded-3xl bg-white p-8 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-amber-600">Teacher Dashboard</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-900">Welcome, Teacher Name</h1>
          </div>
          <button
            onClick={() => navigate('/login')}
            className="inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            Log Out
          </button>
        </header>

        <main className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {[
            'View Account',
            'Manage Elections',
            'Create Election',
            'Election History',
          ].map((label) => (
            <button
              key={label}
              onClick={() => {
                if (label === 'View Account') {
                  localStorage.setItem('backTo', '/teacher-dashboard')
                  return navigate('/view-account', { state: { from: '/teacher-dashboard' } })
                }
                if (label === 'Manage Elections') return navigate('/election-drafts')
                if (label === 'Create Election') return navigate('/create-election')
                if (label === 'Election History') {
                  localStorage.setItem('backTo', '/teacher-dashboard')
                  return navigate('/election-history', { state: { from: '/teacher-dashboard' } })
                }
              }}
              className="group rounded-3xl border border-slate-200 bg-white p-6 text-left shadow-sm transition hover:border-sky-300 hover:shadow-md"
            >
              <div className="text-sm font-semibold text-slate-900">{label}</div>
              <p className="mt-3 text-sm text-slate-500">Open the section</p>
            </button>
          ))}
        </main>
      </div>
    </div>
  )
}

export default TeacherDashboard
