import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getElectionHistory } from '../utils/api.js'
import { Button, Card, Input, PageHeader, PageShell, ResponsiveListTable } from '../components/ui.jsx'

function ElectionHistory() {
  const [elections, setElections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [searchInput, setSearchInput] = useState('')
  const [startDateInput, setStartDateInput] = useState('')
  const [endDateInput, setEndDateInput] = useState('')

  const [searchQuery, setSearchQuery] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const navigate = useNavigate()
  const location = useLocation()
  const returnPath = location.state?.from || localStorage.getItem('backTo') || '/login'
  const role = returnPath.includes('organizer') ? 'organizer' : 'voter'

  useEffect(() => {
    setLoading(true)
    setError(null)
    getElectionHistory({ search: searchQuery, start_date: startDate, end_date: endDate })
      .then((data) => setElections(data || []))
      .catch((err) => setError(err.message || 'Failed to load election history.'))
      .finally(() => setLoading(false))
  }, [searchQuery, startDate, endDate])

  const handleSearch = (e) => {
    e.preventDefault()
    setSearchQuery(searchInput)
    setStartDate(startDateInput)
    setEndDate(endDateInput)
  }

  const fieldLabel = 'text-xs font-medium uppercase tracking-wide text-slate-400'

  return (
    <PageShell>
      <PageHeader
        eyebrow="Elections"
        title="My Election History"
        subtitle="Completed elections and their published results."
        actions={
          <Button variant="secondary" onClick={() => navigate(returnPath)}>
            Back to Dashboard
          </Button>
        }
      />

      <Card>
        <form onSubmit={handleSearch} className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="history-search" className={fieldLabel}>
              Search
            </label>
            <Input
              id="history-search"
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search elections..."
              className="mt-2"
            />
          </div>
          <div>
            <label htmlFor="history-start" className={fieldLabel}>
              Start Date
            </label>
            <Input
              id="history-start"
              type="date"
              value={startDateInput}
              onChange={(e) => setStartDateInput(e.target.value)}
              className="mt-2"
            />
          </div>
          <div>
            <label htmlFor="history-end" className={fieldLabel}>
              End Date
            </label>
            <Input
              id="history-end"
              type="date"
              value={endDateInput}
              onChange={(e) => setEndDateInput(e.target.value)}
              className="mt-2"
            />
          </div>
          <div className="sm:col-span-3">
            <Button type="submit">Apply Filters</Button>
          </div>
        </form>
      </Card>

      <ResponsiveListTable
        primary={{ header: 'Election Title', cell: (e) => e.title }}
        secondary={{
          header: 'Completed',
          cell: (e) => (e.end_date ? new Date(e.end_date).toLocaleDateString() : '—'),
        }}
        action={(e) => (
          <Button
            size="sm"
            onClick={() => navigate('/election-results', { state: { electionId: e.id, role } })}
          >
            View
          </Button>
        )}
        items={elections}
        getKey={(e) => e.id}
        loading={loading}
        error={error}
        loadingMessage="Loading election history..."
        emptyTitle="No elections found."
        emptyMessage="Completed elections will appear here."
      />
    </PageShell>
  )
}

export default ElectionHistory
