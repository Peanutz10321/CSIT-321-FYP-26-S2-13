import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVoteHistory } from '../utils/api'
import { Button, Card, Input, PageHeader, PageShell, ResponsiveListTable } from '../components/ui.jsx'

function VoteHistory() {
  const navigate = useNavigate()
  const [voteHistory, setVoteHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [searchInput, setSearchInput] = useState('')
  const [startDateInput, setStartDateInput] = useState('')
  const [endDateInput, setEndDateInput] = useState('')

  const [searchQuery, setSearchQuery] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  useEffect(() => {
    async function loadVoteHistory() {
      setLoading(true)
      setError(null)
      try {
        const data = await getVoteHistory({ search: searchQuery, start_date: startDate, end_date: endDate })
        setVoteHistory(data)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadVoteHistory()
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
        eyebrow="Voting"
        title="My Vote History"
        subtitle="Receipts for every vote you have cast. Your candidate choice is never stored in plaintext."
        actions={
          <Button variant="secondary" onClick={() => navigate('/voter-dashboard')}>
            Back to Dashboard
          </Button>
        }
      />

      <Card>
        <form onSubmit={handleSearch} className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="vote-search" className={fieldLabel}>
              Search
            </label>
            <Input
              id="vote-search"
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search votes..."
              className="mt-2"
            />
          </div>
          <div>
            <label htmlFor="vote-start" className={fieldLabel}>
              Start Date
            </label>
            <Input
              id="vote-start"
              type="date"
              value={startDateInput}
              onChange={(e) => setStartDateInput(e.target.value)}
              className="mt-2"
            />
          </div>
          <div>
            <label htmlFor="vote-end" className={fieldLabel}>
              End Date
            </label>
            <Input
              id="vote-end"
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
        primary={{ header: 'Election Title', cell: (v) => v.election_title }}
        secondary={{
          header: 'Voted On',
          cell: (v) => (v.submitted_at ? new Date(v.submitted_at).toLocaleDateString() : '—'),
        }}
        action={(v) => (
          <Button size="sm" onClick={() => navigate(`/vote-receipt/${v.id}`)}>
            View
          </Button>
        )}
        items={voteHistory}
        getKey={(v) => v.id}
        loading={loading}
        error={error}
        loadingMessage="Loading vote history..."
        emptyTitle="No vote history found."
        emptyMessage="Votes you cast will appear here with a receipt."
      />
    </PageShell>
  )
}

export default VoteHistory
