import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getCurrentUser } from '../utils/api.js'
import { Button, Card, LoadingState, PageHeader, PageShell } from '../components/ui.jsx'

function AccountRow({ label, children }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-slate-800/70 py-3 last:border-0 sm:flex-row sm:justify-between sm:gap-4">
      <span className="text-sm font-medium text-slate-400">{label}</span>
      <span className="text-sm text-slate-100 sm:text-right">{children}</span>
    </div>
  )
}

function ViewAccount() {
  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'
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

  const roleLabel = user?.role === 'organizer' ? 'Organizer' : 'Voter'

  return (
    <PageShell width="max-w-xl">
      <PageHeader
        eyebrow="Account"
        title={`View ${roleLabel} Account`}
        actions={
          <Button variant="secondary" onClick={() => navigate(returnPath)}>
            Back
          </Button>
        }
      />

      <Card padded={!!user}>
        {!user ? (
          <LoadingState message="Loading account..." />
        ) : (
          <div className="text-sm">
            <AccountRow label="Username">{user.username || '—'}</AccountRow>
            <AccountRow label={`${roleLabel} Email`}>{user.email || '—'}</AccountRow>
            <AccountRow label="Password">••••••••</AccountRow>
            <AccountRow label="Full Name">{user.full_name || '—'}</AccountRow>
            <AccountRow label="External ID">{user.external_id || '—'}</AccountRow>
          </div>
        )}
      </Card>

      <Button fullWidth size="lg" onClick={() => navigate('/update-account')}>
        Update User Account
      </Button>
    </PageShell>
  )
}

export default ViewAccount
