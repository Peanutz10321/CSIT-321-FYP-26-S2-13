import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { viewUser, getCurrentUser, updateUserStatus } from '../utils/api.js'
import {
  Button,
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  PageShell,
  StatusBadge,
} from '../components/ui.jsx'

const STATUS_LABEL = {
  active: 'Active',
  inactive: 'Inactive',
  suspended: 'Suspended',
}

const STATUS_TONE = {
  active: 'emerald',
  inactive: 'amber',
  suspended: 'rose',
}

// Module-level so React does not recreate it on each render.
function MetaRow({ label, children }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-slate-800/70 py-3 last:border-0 sm:flex-row sm:justify-between sm:gap-4">
      <span className="text-sm font-medium text-slate-400">{label}</span>
      <span className="text-sm text-slate-100 sm:text-right">{children}</span>
    </div>
  )
}

function AdminViewUser() {
  const navigate = useNavigate()
  const { userId } = useParams()
  const [currentUser, setCurrentUser] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    Promise.all([getCurrentUser(), viewUser(userId)])
      .then(([me, target]) => {
        setCurrentUser(me)
        setUser(target)
      })
      .catch((err) => {
        if (err.message?.toLowerCase().includes('not authenticated')) {
          navigate('/login')
          return
        }
        setError(err.message || 'Failed to load user.')
      })
      .finally(() => setLoading(false))
  }, [userId, navigate])

  async function handleToggleSuspend() {
    const newStatus = user.status === 'suspended' ? 'active' : 'suspended'
    setToggling(true)
    try {
      const updated = await updateUserStatus(user.id, newStatus)
      setUser(updated)
    } catch (err) {
      alert(`Failed to update status: ${err.message}`)
    } finally {
      setToggling(false)
    }
  }

  const isAdmin = currentUser?.role === 'system_admin'
  const canToggle = isAdmin && currentUser?.id !== user?.id
  const isSuspended = user?.status === 'suspended'

  return (
    <PageShell width="max-w-xl">
      <PageHeader
        eyebrow="Admin"
        title="View User Account"
        actions={
          <Button variant="secondary" onClick={() => navigate('/manage-users')}>
            Back
          </Button>
        }
      />

      {error && <ErrorState message={error} />}

      {loading ? (
        <Card padded={false}>
          <LoadingState message="Loading user..." />
        </Card>
      ) : (
        user && (
          <Card>
            <div className="text-sm">
              <MetaRow label="Username">{user.username || '—'}</MetaRow>
              <MetaRow label="Email">{user.email || '—'}</MetaRow>
              <MetaRow label="Full Name">{user.full_name || '—'}</MetaRow>
              <MetaRow label="External ID">{user.external_id || '—'}</MetaRow>
              <MetaRow label="Account Type">
                <span className="capitalize">{user.role?.replace('_', ' ') || '—'}</span>
              </MetaRow>
              <MetaRow label="Status">
                <StatusBadge tone={STATUS_TONE[user.status] ?? 'slate'}>
                  {STATUS_LABEL[user.status] ?? user.status ?? '—'}
                </StatusBadge>
              </MetaRow>
            </div>

            {canToggle && (
              <div className="mt-6 border-t border-slate-800 pt-6">
                <Button
                  fullWidth
                  variant={isSuspended ? 'success' : 'danger'}
                  onClick={handleToggleSuspend}
                  disabled={toggling}
                >
                  {toggling
                    ? 'Updating...'
                    : isSuspended
                      ? 'Unsuspend Account'
                      : 'Suspend Account'}
                </Button>
              </div>
            )}
          </Card>
        )
      )}
    </PageShell>
  )
}

export default AdminViewUser
