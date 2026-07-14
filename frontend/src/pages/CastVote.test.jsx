import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import CastVote from './CastVote.jsx'
import { getCurrentUser, getElectionDetails, getVoteHistory, submitVote } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  getCurrentUser: vi.fn(),
  getElectionDetails: vi.fn(),
  getVoteHistory: vi.fn(),
  submitVote: vi.fn(),
}))

const singleElection = {
  id: 'e1',
  title: 'Club Election',
  status: 'active',
  ballot_type: 'single',
  max_selections: 1,
  candidates: [
    { id: 'c1', name: 'Alice' },
    { id: 'c2', name: 'Bob' },
  ],
}

const multiElection = {
  ...singleElection,
  ballot_type: 'multi',
  max_selections: 2,
  candidates: [
    { id: 'c1', name: 'Alice' },
    { id: 'c2', name: 'Bob' },
    { id: 'c3', name: 'Carol' },
  ],
}

async function renderCastVote(election, history = []) {
  getCurrentUser.mockResolvedValue({ id: 'u1', role: 'voter', external_id: 'INST-1' })
  getElectionDetails.mockResolvedValue(election)
  getVoteHistory.mockResolvedValue(history)

  render(
    <MemoryRouter initialEntries={[{ pathname: '/cast-vote', state: { electionId: 'e1' } }]}>
      <Routes>
        <Route path="/cast-vote" element={<CastVote />} />
      </Routes>
    </MemoryRouter>,
  )

  await screen.findByText('Cast Your Vote')
}

describe('CastVote ballot flexibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders radios for a single ballot and keeps exactly one candidate selected', async () => {
    await renderCastVote(singleElection)

    // Two candidates + the abstain option share one radio group.
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)

    fireEvent.click(screen.getByRole('radio', { name: 'Alice' }))
    expect(screen.getByRole('radio', { name: 'Alice' })).toBeChecked()

    fireEvent.click(screen.getByRole('radio', { name: 'Bob' }))
    expect(screen.getByRole('radio', { name: 'Bob' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Alice' })).not.toBeChecked()
  })

  it('renders checkboxes for a multi ballot', async () => {
    await renderCastVote(multiElection)

    // Three candidates + the abstain option.
    expect(screen.getAllByRole('checkbox')).toHaveLength(4)
    expect(screen.queryAllByRole('radio')).toHaveLength(0)
  })

  it('enforces max_selections without silently removing an existing selection', async () => {
    await renderCastVote(multiElection)

    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }))

    // At the limit the remaining candidate is disabled, prior picks stay intact.
    expect(screen.getByRole('checkbox', { name: 'Carol' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Alice' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Bob' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Carol' })).not.toBeChecked()
  })

  it('displays a live selection count for multi ballots', async () => {
    await renderCastVote(multiElection)

    expect(screen.getByText('0 of 2 selections')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }))
    expect(screen.getByText('1 of 2 selections')).toBeInTheDocument()
  })

  it('abstain clears candidate selections', async () => {
    await renderCastVote(multiElection)

    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /abstain/i }))

    expect(screen.getByRole('checkbox', { name: /abstain/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Alice' })).not.toBeChecked()
  })

  it('selecting a candidate clears abstention', async () => {
    await renderCastVote(singleElection)

    fireEvent.click(screen.getByRole('radio', { name: /abstain/i }))
    expect(screen.getByRole('radio', { name: /abstain/i })).toBeChecked()

    fireEvent.click(screen.getByRole('radio', { name: 'Alice' }))
    expect(screen.getByRole('radio', { name: 'Alice' })).toBeChecked()
    expect(screen.getByRole('radio', { name: /abstain/i })).not.toBeChecked()
  })

  it('cannot submit without a candidate selection or explicit abstention', async () => {
    await renderCastVote(singleElection)

    expect(screen.getByRole('button', { name: 'Submit Vote' })).toBeDisabled()

    fireEvent.click(screen.getByRole('radio', { name: /abstain/i }))
    expect(screen.getByRole('button', { name: 'Submit Vote' })).toBeEnabled()
  })

  it('single ballot submits candidate_ids with the one selected id', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    submitVote.mockResolvedValue({ id: 'v1', candidate_names: ['Alice'], abstained: false })
    await renderCastVote(singleElection)

    fireEvent.click(screen.getByRole('radio', { name: 'Alice' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Vote' }))

    await waitFor(() =>
      expect(submitVote).toHaveBeenCalledWith({ election_id: 'e1', candidate_ids: ['c1'] }),
    )
    // The receipt receives the immediate response through in-memory state only.
    expect(navigateMock).toHaveBeenCalledWith('/vote-receipt/v1', {
      state: { submittedVote: expect.objectContaining({ id: 'v1' }) },
    })
  })

  it('multi ballot submits every selected id', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    submitVote.mockResolvedValue({ id: 'v2', candidate_names: ['Alice', 'Bob'], abstained: false })
    await renderCastVote(multiElection)

    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Vote' }))

    await waitFor(() =>
      expect(submitVote).toHaveBeenCalledWith({ election_id: 'e1', candidate_ids: ['c1', 'c2'] }),
    )
  })

  it('abstention submits an empty candidate_ids list', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    submitVote.mockResolvedValue({ id: 'v3', candidate_names: [], abstained: true })
    await renderCastVote(multiElection)

    fireEvent.click(screen.getByRole('checkbox', { name: /abstain/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Vote' }))

    await waitFor(() =>
      expect(submitVote).toHaveBeenCalledWith({ election_id: 'e1', candidate_ids: [] }),
    )
  })

  it('an existing vote prevents resubmission', async () => {
    await renderCastVote(singleElection, [{ id: 'v9', election_id: 'e1' }])

    const button = screen.getByRole('button', { name: 'Voted' })
    expect(button).toBeDisabled()
    expect(submitVote).not.toHaveBeenCalled()
  })

  it('confirmation names the selection, all selections, or the abstention', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await renderCastVote(multiElection)

    fireEvent.click(screen.getByRole('checkbox', { name: 'Alice' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Vote' }))
    expect(confirmSpy).toHaveBeenLastCalledWith(expect.stringContaining('Alice, Bob'))

    fireEvent.click(screen.getByRole('checkbox', { name: 'Bob' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Vote' }))
    expect(confirmSpy).toHaveBeenLastCalledWith(expect.stringContaining('Alice'))

    fireEvent.click(screen.getByRole('checkbox', { name: /abstain/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Vote' }))
    expect(confirmSpy).toHaveBeenLastCalledWith(expect.stringMatching(/abstain/i))

    // Declining the confirmation never submits.
    expect(submitVote).not.toHaveBeenCalled()
  })
})
