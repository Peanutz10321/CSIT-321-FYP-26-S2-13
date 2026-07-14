import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import CreateElection from './CreateElection.jsx'
import {
  createElection,
  createElectionDraft,
  getElectionDrafts,
  getEligibleVoters,
} from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  createElection: vi.fn(),
  createElectionDraft: vi.fn(),
  getElectionDrafts: vi.fn(),
  getEligibleVoters: vi.fn(),
}))

function renderCreate(drafts = []) {
  getElectionDrafts.mockResolvedValue(drafts)
  render(
    <MemoryRouter>
      <CreateElection />
    </MemoryRouter>,
  )
}

function fillBasics({ candidates = 'Alice, Bob', voters = 'V1' } = {}) {
  fireEvent.change(screen.getByPlaceholderText('Election title'), {
    target: { value: 'Test Election' },
  })
  fireEvent.change(screen.getByPlaceholderText('Comma or newline separated names'), {
    target: { value: candidates },
  })
  fireEvent.change(screen.getByPlaceholderText('Comma or newline separated external IDs'), {
    target: { value: voters },
  })
}

describe('CreateElection ballot configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to a single-choice ballot with no max selections input', () => {
    renderCreate()

    expect(screen.getByRole('radio', { name: 'Single choice' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Multiple choice' })).not.toBeChecked()
    expect(screen.queryByLabelText('Maximum selections')).not.toBeInTheDocument()
  })

  it('switching to multiple choice reveals the max selections input', () => {
    renderCreate()

    fireEvent.click(screen.getByRole('radio', { name: 'Multiple choice' }))

    expect(screen.getByLabelText('Maximum selections')).toHaveValue(1)
  })

  it('active creation sends ballot_type and max_selections in the payload', async () => {
    createElection.mockResolvedValue({ id: 'e9' })
    renderCreate()

    fillBasics()
    fireEvent.click(screen.getByRole('radio', { name: 'Multiple choice' }))
    fireEvent.change(screen.getByLabelText('Maximum selections'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() =>
      expect(createElection).toHaveBeenCalledWith(
        expect.objectContaining({ ballot_type: 'multi', max_selections: 2 }),
      ),
    )
  })

  it('a draft may keep an incomplete multi configuration', async () => {
    createElectionDraft.mockResolvedValue({ id: 'd9' })
    renderCreate()

    // Only two candidates, but a draft may hold max_selections beyond that —
    // the backend validates the final count at activation.
    fillBasics({ candidates: 'Alice, Bob' })
    fireEvent.click(screen.getByRole('radio', { name: 'Multiple choice' }))
    fireEvent.change(screen.getByLabelText('Maximum selections'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() =>
      expect(createElectionDraft).toHaveBeenCalledWith(
        expect.objectContaining({ ballot_type: 'multi', max_selections: 3 }),
      ),
    )
  })

  it('active creation rejects max selections above the candidate count with an inline message', async () => {
    renderCreate()

    fillBasics({ candidates: 'Alice, Bob' })
    fireEvent.click(screen.getByRole('radio', { name: 'Multiple choice' }))
    fireEvent.change(screen.getByLabelText('Maximum selections'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Maximum selections cannot exceed the number of candidates (2).',
    )
    expect(createElection).not.toHaveBeenCalled()
  })

  it('zero or invalid max selections is rejected, never silently clamped', async () => {
    renderCreate()

    fillBasics()
    fireEvent.click(screen.getByRole('radio', { name: 'Multiple choice' }))
    fireEvent.change(screen.getByLabelText('Maximum selections'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Maximum selections must be a whole number of at least 1.',
    )
    expect(createElection).not.toHaveBeenCalled()
    // The invalid value stays visible for the organizer to correct.
    expect(screen.getByLabelText('Maximum selections')).toHaveValue(0)
  })

  it('loading a draft restores its ballot configuration and + New resets it', async () => {
    getEligibleVoters.mockResolvedValue([])
    renderCreate([
      {
        id: 'd1',
        title: 'Draft X',
        ballot_type: 'multi',
        max_selections: 2,
        end_date: null,
        candidates: [{ name: 'A' }, { name: 'B' }],
      },
    ])

    fireEvent.click(await screen.findByRole('button', { name: 'Draft X' }))

    await waitFor(() =>
      expect(screen.getByRole('radio', { name: 'Multiple choice' })).toBeChecked(),
    )
    expect(screen.getByLabelText('Maximum selections')).toHaveValue(2)

    // Starting a new form resets to single / 1.
    fireEvent.click(screen.getByRole('button', { name: '+ New' }))
    expect(screen.getByRole('radio', { name: 'Single choice' })).toBeChecked()
    expect(screen.queryByLabelText('Maximum selections')).not.toBeInTheDocument()
  })
})
