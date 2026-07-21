import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, logout } from '../utils/api.js'
import { Button, Card, PageHeader, PageShell, StatusBadge } from '../components/ui.jsx'

function ArrowIcon({ className = 'h-4 w-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function AdminDashboard() {
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

  return (
    <PageShell>
      <PageHeader
        eyebrow="Admin"
        title={`Welcome, ${user?.username || 'Admin'}`}
        subtitle="Manage user accounts across the system."
        actions={
          <Button
            variant="secondary"
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            Log Out
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {/* Primary admin action */}
        <Card
          as="button"
          onClick={() => navigate('/manage-users')}
          className="group flex h-full w-full flex-col border-blue-500/40 bg-blue-500/10 text-left transition hover:border-blue-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
        >
          <h2 className="text-base font-semibold text-slate-100 group-hover:text-blue-300">
            Manage User Accounts
          </h2>
          <p className="mt-2 flex-1 text-sm text-slate-400">
            View users, review their details, and suspend or reinstate accounts.
          </p>
          <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-blue-400">
            Open
            <ArrowIcon className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </span>
        </Card>

        {/* System overview — who you are signed in as */}
        <Card className="flex h-full flex-col">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Signed in as</p>
          <p className="mt-2 text-lg font-semibold text-slate-100">{user?.username || '—'}</p>
          <div className="mt-3">
            <StatusBadge tone="rose">System Administrator</StatusBadge>
          </div>
          <p className="mt-4 flex-1 text-sm text-slate-400">
            Administrator access is limited to managing user accounts. Elections and ballots are
            handled by organizers and voters.
          </p>
        </Card>
      </div>
    </PageShell>
  )
}

export default AdminDashboard
