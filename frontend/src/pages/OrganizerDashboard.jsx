import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUser, logout } from '../utils/api.js'
import { Button, Card, PageHeader, PageShell } from '../components/ui.jsx'

function ArrowIcon({ className = 'h-4 w-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// A dashboard tile — the whole card is the clickable action.
function ActionCard({ title, description, onClick, highlight = false }) {
  return (
    <Card
      as="button"
      onClick={onClick}
      className={`group flex h-full w-full flex-col text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${
        highlight
          ? 'border-blue-500/40 bg-blue-500/10 hover:border-blue-400'
          : 'hover:border-blue-400/60'
      }`}
    >
      <h2 className="text-base font-semibold text-slate-100 group-hover:text-blue-300">{title}</h2>
      <p className="mt-2 flex-1 text-sm text-slate-400">{description}</p>
      <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-blue-400">
        {highlight ? 'Start now' : 'Open'}
        <ArrowIcon className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Card>
  )
}

function OrganizerDashboard() {
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
    localStorage.setItem('backTo', '/organizer-dashboard')
    navigate('/view-account', { state: { from: '/organizer-dashboard' } })
  }

  const goToHistory = () => {
    localStorage.setItem('backTo', '/organizer-dashboard')
    navigate('/election-history', { state: { from: '/organizer-dashboard' } })
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow="Organizer"
        title={`Welcome, ${user?.username || 'Organizer'}`}
        subtitle="Create and manage your voting events, then review results once they close."
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
        <ActionCard
          title="New Election"
          description="Set up a new voting event — candidates, deadline, ballot type, and eligible voters."
          onClick={() => navigate('/create-election')}
          highlight
        />
        <ActionCard
          title="My Active Elections"
          description="View elections that are currently open and manage their details."
          onClick={() => navigate('/active-elections')}
        />
        <ActionCard
          title="My Election History"
          description="Review completed elections and their published results."
          onClick={goToHistory}
        />
        <ActionCard
          title="View User Account"
          description="See and update your organizer profile details."
          onClick={goToAccount}
        />
      </div>
    </PageShell>
  )
}

export default OrganizerDashboard
