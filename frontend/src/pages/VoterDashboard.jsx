import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, logout } from '../utils/api.js'
import { Button, LockIcon, PageShell } from '../components/ui.jsx'

// Module-level so it is not recreated on every render.
function ActionCard({ label, description, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-full flex-col justify-between gap-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 text-left shadow-lg shadow-slate-950/40 transition hover:border-blue-500/60 hover:bg-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
    >
      <div>
        <h2 className="text-base font-semibold text-slate-100">{label}</h2>
        {description && <p className="mt-2 text-sm text-slate-400">{description}</p>}
      </div>
      <span className="text-sm font-medium text-blue-400 transition group-hover:translate-x-0.5">
        Open <span aria-hidden="true">→</span>
      </span>
    </button>
  )
}

function VoterDashboard() {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)

  useEffect(() => {
    const token = localStorage.getItem('authToken')
    if (!token) {
      navigate('/login')
      return
    }

    getCurrentUser()
      .then(setUser)
      .catch(() => navigate('/login'))
  }, [navigate])

  const goToAccount = () => {
    localStorage.setItem('backTo', '/voter-dashboard')
    navigate('/view-account', { state: { from: '/voter-dashboard' } })
  }
  const goToElectionHistory = () => {
    localStorage.setItem('backTo', '/voter-dashboard')
    navigate('/election-history', { state: { from: '/voter-dashboard' } })
  }

  const secondaryActions = [
    { label: 'My Vote History', description: 'Review receipts for votes you have cast.', onClick: () => navigate('/vote-history') },
    { label: 'My Election History', description: 'Browse completed elections and results.', onClick: goToElectionHistory },
    { label: 'View User Account', description: 'See and update your profile details.', onClick: goToAccount },
  ]

  return (
    <PageShell width="max-w-5xl">
      <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-lg shadow-slate-950/40 sm:flex-row sm:items-center sm:justify-between sm:p-7">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-400">Voter Dashboard</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
            Welcome, {user?.username || 'Voter'}
          </h1>
        </div>
        <Button variant="secondary" onClick={() => { logout(); navigate('/login') }} className="self-start sm:self-auto">
          Log Out
        </Button>
      </header>

      {/* Primary next action */}
      <section className="relative overflow-hidden rounded-2xl border border-blue-500/30 bg-slate-900/70 p-6 shadow-lg shadow-blue-950/30 sm:p-8">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_120%_at_10%_0%,rgba(37,99,235,0.15),transparent_70%)]" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-xl">
            <span className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-blue-300">
              <LockIcon className="h-3.5 w-3.5" />
              Ready to vote
            </span>
            <h2 className="mt-3 text-xl font-semibold text-slate-100">Your active elections</h2>
            <p className="mt-2 text-sm text-slate-400">
              View the elections you are eligible for and cast your encrypted ballot.
            </p>
          </div>
          <Button size="lg" onClick={() => navigate('/active-elections')} className="shrink-0">
            Go to Active Elections
          </Button>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {secondaryActions.map((action) => (
          <ActionCard key={action.label} {...action} />
        ))}
      </div>
    </PageShell>
  )
}

export default VoterDashboard
