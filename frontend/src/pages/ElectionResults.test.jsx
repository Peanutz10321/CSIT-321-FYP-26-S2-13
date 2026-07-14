import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import ElectionResults from './ElectionResults.jsx'
import { getElectionDetails, getElectionResults, getEligibleVoters } from '../utils/api.js'

vi.mock('../utils/api.js', () => ({
  getElectionDetails: vi.fn(),
  getElectionResults: vi.fn(),
  getEligibleVoters: vi.fn(),
}))

const multiElection = {
  id: 'e1',
  title: 'Club Election',
  ballot_type: 'multi',
  max_selections: 2,
  organizer_username: 'org1',
  start_date: '2026-06-30T10:00:00',
  end_date: '2026-07-02T10:00:00',
  candidates: [
    { id: 'c1', name: 'Alice' },
    { id: 'c2', name: 'Bob' },
    { id: 'c3', name: 'Carol' },
  ],
}

const singleElection = { ...multiElection, ballot_type: 'single', max_selections: 1 }

// Two multi-select ballots (Alice+Bob, Alice+Carol) plus one abstention:
// candidate totals sum to 4 while turnout is 3 ballots.
const multiResults = {
  election_id: 'e1',
  election_title: 'Club Election',
  status: 'completed',
  total_votes: 3,
  winner: 'Alice',
  tied_candidates: [],
  results: [
    { candidate_id: 'c1', candidate_name: 'Alice', total_votes: 2 },
    { candidate_id: 'c2', candidate_name: 'Bob', total_votes: 1 },
    { candidate_id: 'c3', candidate_name: 'Carol', total_votes: 1 },
  ],
}

async function renderResults(election, results) {
  getElectionDetails.mockResolvedValue(election)
  getElectionResults.mockResolvedValue(results)
  getEligibleVoters.mockResolvedValue([])

  render(
    <MemoryRouter
      initialEntries={[{ pathname: '/election-results', state: { electionId: 'e1', role: 'voter' } }]}
    >
      <Routes>
        <Route path="/election-results" element={<ElectionResults />} />
      </Routes>
    </MemoryRouter>,
  )

  await screen.findByText('Election Results')
}

function row(label) {
  return screen.getByText(`${label}:`).closest('div')
}

describe('ElectionResults turnout and labels', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays turnout from the backend total_votes, never the sum of candidate totals', async () => {
    await renderResults(multiElection, multiResults)

    const turnoutRow = row('Total Ballots Cast')
    // Backend turnout is 3; the candidate totals sum to 4 and must not be shown.
    expect(turnoutRow).toHaveTextContent('3')
    expect(turnoutRow).not.toHaveTextContent('4')
  })

  it('labels candidate counts as selections for a multi ballot', async () => {
    await renderResults(multiElection, multiResults)

    expect(row('Selections Per Candidate')).toHaveTextContent('Alice: 2, Bob: 1, Carol: 1')
    expect(screen.queryByText('Votes Per Candidate:')).not.toBeInTheDocument()
  })

  it('labels candidate counts as votes for a single ballot', async () => {
    await renderResults(singleElection, { ...multiResults, total_votes: 4 })

    expect(row('Votes Per Candidate')).toBeInTheDocument()
    expect(screen.queryByText('Selections Per Candidate:')).not.toBeInTheDocument()
  })

  it('shows turnout with no winner when every ballot is an abstention', async () => {
    await renderResults(multiElection, {
      ...multiResults,
      total_votes: 2,
      winner: null,
      tied_candidates: [],
      results: multiResults.results.map((r) => ({ ...r, total_votes: 0 })),
    })

    expect(row('Total Ballots Cast')).toHaveTextContent('2')
    expect(row('Winner')).toHaveTextContent('—')
  })
})
