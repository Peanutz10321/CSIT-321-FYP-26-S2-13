import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import CreateElection from './CreateElection.jsx'
import {
  activateElection,
  createElection,
  createElectionDraft,
  getElectionDrafts,
  getEligibleVoters,
  updateElection,
} from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  activateElection: vi.fn(),
  createElection: vi.fn(),
  createElectionDraft: vi.fn(),
  getElectionDrafts: vi.fn(),
  getEligibleVoters: vi.fn(),
  updateElection: vi.fn(),
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

// A draft the sidebar can offer, already carrying a full configuration.
const savedDraft = {
  id: 'draft-1',
  title: 'Saved Draft',
  ballot_type: 'single',
  max_selections: 1,
  end_date: null,
  candidates: [{ name: 'Alice' }, { name: 'Bob' }],
}

async function openSavedDraft() {
  fireEvent.click(await screen.findByRole('button', { name: 'Saved Draft' }))
  await waitFor(() => expect(getEligibleVoters).toHaveBeenCalledWith('draft-1'))
}

describe('CreateElection draft lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom has no alert; the page uses it as its error surface.
    vi.spyOn(window, 'alert').mockImplementation(() => {})
  })

  it('saving with no draft selected creates one and keeps its existing api name', async () => {
    createElectionDraft.mockResolvedValue({ id: 'draft-new' })
    renderCreate()

    fillBasics({ candidates: 'Alice, Bob', voters: 'V1, V2' })
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() => expect(createElectionDraft).toHaveBeenCalledTimes(1))
    expect(updateElection).not.toHaveBeenCalled()

    // Candidates and eligible voters both belong to the draft payload.
    expect(createElectionDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Test Election',
        candidates: [
          expect.objectContaining({ name: 'Alice', display_order: 1 }),
          expect.objectContaining({ name: 'Bob', display_order: 2 }),
        ],
        eligible_voter_external_ids: ['V1', 'V2'],
      }),
    )

    // The sidebar is refreshed after saving (once on mount, once after the save).
    await waitFor(() => expect(getElectionDrafts).toHaveBeenCalledTimes(2))
  })

  it('saving again after creating a draft updates that same id instead of forking', async () => {
    createElectionDraft.mockResolvedValue({ id: 'draft-new' })
    updateElection.mockResolvedValue({ id: 'draft-new' })
    renderCreate()

    fillBasics()
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))
    await waitFor(() => expect(createElectionDraft).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByPlaceholderText('Election title'), {
      target: { value: 'Renamed Election' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() =>
      expect(updateElection).toHaveBeenCalledWith(
        'draft-new',
        expect.objectContaining({ title: 'Renamed Election' }),
      ),
    )
    // Still exactly one creation: the draft count never grows.
    expect(createElectionDraft).toHaveBeenCalledTimes(1)
  })

  it('saving an opened draft updates it and never creates a second draft', async () => {
    getEligibleVoters.mockResolvedValue([{ voter_external_id: 'V1' }])
    updateElection.mockResolvedValue({ id: 'draft-1' })
    renderCreate([savedDraft])

    await openSavedDraft()

    fireEvent.change(screen.getByPlaceholderText('Comma or newline separated external IDs'), {
      target: { value: 'V1, V2' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() =>
      expect(updateElection).toHaveBeenCalledWith(
        'draft-1',
        expect.objectContaining({
          title: 'Saved Draft',
          eligible_voter_external_ids: ['V1', 'V2'],
        }),
      ),
    )
    expect(createElectionDraft).not.toHaveBeenCalled()

    // Sidebar refreshed, and the draft stays selected.
    await waitFor(() => expect(getElectionDrafts).toHaveBeenCalledTimes(2))
    expect(screen.getByRole('button', { name: '+ New' })).toBeInTheDocument()
  })

  it('publishing a selected draft updates then activates the same id', async () => {
    getEligibleVoters.mockResolvedValue([{ voter_external_id: 'V1' }])
    updateElection.mockResolvedValue({ id: 'draft-1' })
    activateElection.mockResolvedValue({ id: 'draft-1', status: 'active' })
    renderCreate([savedDraft])

    await openSavedDraft()

    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(activateElection).toHaveBeenCalledWith('draft-1'))
    expect(updateElection).toHaveBeenCalledWith('draft-1', expect.objectContaining({
      eligible_voter_external_ids: ['V1'],
    }))
    // No second active election is created alongside the draft.
    expect(createElection).not.toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/election-detail', {
      state: { electionId: 'draft-1', from: 'active', role: 'organizer' },
    })
  })

  it('a failed activation leaves the draft in place and surfaces the error', async () => {
    getEligibleVoters.mockResolvedValue([{ voter_external_id: 'V1' }])
    updateElection.mockResolvedValue({ id: 'draft-1' })
    activateElection.mockRejectedValue(new Error('Election must have a deadline before activation'))
    renderCreate([savedDraft])

    await openSavedDraft()

    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith(
        'Failed to create election: Election must have a deadline before activation',
      ),
    )
    // The edits were saved, so the election survives as a recoverable draft.
    expect(updateElection).toHaveBeenCalledWith('draft-1', expect.anything())
    expect(navigateMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled()
  })

  it('creating with no draft selected still uses the direct creation flow', async () => {
    createElection.mockResolvedValue({ id: 'e-new' })
    renderCreate()

    fillBasics({ candidates: 'Alice, Bob', voters: 'V1' })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() =>
      expect(createElection).toHaveBeenCalledWith(
        expect.objectContaining({ eligible_voter_external_ids: ['V1'] }),
      ),
    )
    expect(updateElection).not.toHaveBeenCalled()
    expect(activateElection).not.toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/election-detail', {
      state: { electionId: 'e-new', from: 'active', role: 'organizer' },
    })
  })
})

describe('CreateElection draft snapshot loading', () => {
  const draftA = {
    id: 'draft-a',
    title: 'Draft A',
    ballot_type: 'single',
    max_selections: 1,
    end_date: null,
    candidates: [{ name: 'Alice', description: 'From A', photo_url: null, display_order: 1 }],
  }
  const draftB = {
    id: 'draft-b',
    title: 'Draft B',
    ballot_type: 'single',
    max_selections: 1,
    end_date: null,
    candidates: [{ name: 'Bob' }],
  }

  const votersField = () =>
    screen.getByPlaceholderText('Comma or newline separated external IDs')

  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'alert').mockImplementation(() => {})
  })

  it('a slow load for one draft never lands in the draft selected after it', async () => {
    // draft-a resolves only after draft-b has already been selected and loaded.
    let resolveA
    getEligibleVoters.mockImplementation((id) =>
      id === 'draft-a'
        ? new Promise((resolve) => {
            resolveA = resolve
          })
        : Promise.resolve([{ voter_external_id: 'B-VOTER' }]),
    )
    updateElection.mockResolvedValue({ id: 'draft-b' })
    renderCreate([draftA, draftB])

    fireEvent.click(await screen.findByRole('button', { name: 'Draft A' }))
    fireEvent.click(screen.getByRole('button', { name: 'Draft B' }))

    await waitFor(() => expect(votersField()).toHaveValue('B-VOTER'))

    // draft-a's response arrives late; it must be discarded, not written into the form.
    resolveA([{ voter_external_id: 'A-VOTER' }])
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled())
    expect(votersField()).toHaveValue('B-VOTER')

    // And the save that follows carries draft B's voters against draft B's id.
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))
    await waitFor(() =>
      expect(updateElection).toHaveBeenCalledWith(
        'draft-b',
        expect.objectContaining({ eligible_voter_external_ids: ['B-VOTER'] }),
      ),
    )
  })

  it('save and create are disabled while the selected draft is still loading', async () => {
    let resolveVoters
    getEligibleVoters.mockReturnValue(
      new Promise((resolve) => {
        resolveVoters = resolve
      }),
    )
    renderCreate([draftA])

    fireEvent.click(await screen.findByRole('button', { name: 'Draft A' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save Election Draft' })).toBeDisabled(),
    )
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()

    resolveVoters([{ voter_external_id: 'A-VOTER' }])

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save Election Draft' })).toBeEnabled(),
    )
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled()
  })

  it('a failed voter load shows an error and saving leaves the stored list alone', async () => {
    getEligibleVoters.mockRejectedValue(new Error('network down'))
    updateElection.mockResolvedValue({ id: 'draft-a' })
    renderCreate([draftA])

    fireEvent.click(await screen.findByRole('button', { name: 'Draft A' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Could not load this draft.s eligible voters/,
    )
    // The form is usable again â€” the failure blocks nothing but the voter list.
    expect(screen.getByRole('button', { name: 'Save Election Draft' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() => expect(updateElection).toHaveBeenCalledTimes(1))
    const [, payload] = updateElection.mock.calls[0]
    // Omitted, not empty: an empty list would wipe the draft's real voters.
    expect(payload).not.toHaveProperty('eligible_voter_external_ids')
  })

  it('typing voters after a failed load submits what the organizer entered', async () => {
    getEligibleVoters.mockRejectedValue(new Error('network down'))
    updateElection.mockResolvedValue({ id: 'draft-a' })
    renderCreate([draftA])

    fireEvent.click(await screen.findByRole('button', { name: 'Draft A' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    fireEvent.change(votersField(), { target: { value: 'TYPED-1, TYPED-2' } })
    // Taking over the field clears the warning about it.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() =>
      expect(updateElection).toHaveBeenCalledWith(
        'draft-a',
        expect.objectContaining({ eligible_voter_external_ids: ['TYPED-1', 'TYPED-2'] }),
      ),
    )
  })

  it('starting a new form discards a load still in flight', async () => {
    let resolveVoters
    getEligibleVoters.mockReturnValue(
      new Promise((resolve) => {
        resolveVoters = resolve
      }),
    )
    createElectionDraft.mockResolvedValue({ id: 'draft-new', candidates: [] })
    renderCreate([draftA])

    fireEvent.click(await screen.findByRole('button', { name: 'Draft A' }))
    fireEvent.click(screen.getByRole('button', { name: '+ New' }))

    resolveVoters([{ voter_external_id: 'A-VOTER' }])
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save Election Draft' })).toBeEnabled(),
    )
    expect(votersField()).toHaveValue('')

    // The blank form creates a fresh draft rather than updating draft A.
    fillBasics({ voters: 'NEW-VOTER' })
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() => expect(createElectionDraft).toHaveBeenCalledTimes(1))
    expect(updateElection).not.toHaveBeenCalled()
  })
})

describe('CreateElection draft update payload', () => {
  const draftWithMeta = {
    id: 'draft-m',
    title: 'Draft M',
    ballot_type: 'single',
    max_selections: 1,
    end_date: '2026-09-01T10:00:00',
    candidates: [
      { name: 'Alice', description: 'Incumbent', photo_url: 'https://example.test/a.png', display_order: 1 },
      { name: 'Bob', description: null, photo_url: null, display_order: 2 },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    getEligibleVoters.mockResolvedValue([{ voter_external_id: 'V1' }])
  })

  async function openDraftM() {
    renderCreate([draftWithMeta])
    fireEvent.click(await screen.findByRole('button', { name: 'Draft M' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled())
  }

  it('omits start_date and keeps stored candidate metadata', async () => {
    updateElection.mockResolvedValue({ id: 'draft-m' })
    await openDraftM()

    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() => expect(updateElection).toHaveBeenCalledTimes(1))
    const [id, payload] = updateElection.mock.calls[0]
    expect(id).toBe('draft-m')
    // The form never shows start_date, so it must not push a new one.
    expect(payload).not.toHaveProperty('start_date')
    // It never shows description/photo_url either â€” those ride through untouched.
    expect(payload.candidates).toEqual([
      { name: 'Alice', description: 'Incumbent', photo_url: 'https://example.test/a.png', display_order: 1 },
      { name: 'Bob', description: null, photo_url: null, display_order: 2 },
    ])
  })

  it('sends an explicit null end_date when the organizer clears the deadline', async () => {
    updateElection.mockResolvedValue({ id: 'draft-m' })
    await openDraftM()

    expect(screen.getByLabelText('Deadline')).toHaveValue('2026-09-01T10:00')
    fireEvent.change(screen.getByLabelText('Deadline'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() => expect(updateElection).toHaveBeenCalledTimes(1))
    const [, payload] = updateElection.mock.calls[0]
    // Present and null â€” the backend reads that as "clear it", not "not supplied".
    expect(payload).toHaveProperty('end_date', null)
  })

  it('sends an empty candidate list when the organizer clears the box', async () => {
    updateElection.mockResolvedValue({ id: 'draft-m' })
    await openDraftM()

    fireEvent.change(screen.getByPlaceholderText('Comma or newline separated names'), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save Election Draft' }))

    await waitFor(() => expect(updateElection).toHaveBeenCalledTimes(1))
    expect(updateElection.mock.calls[0][1].candidates).toEqual([])
  })

  it('publishing updates before it activates, on the one id', async () => {
    const order = []
    updateElection.mockImplementation(async () => {
      order.push('update')
      return { id: 'draft-m' }
    })
    activateElection.mockImplementation(async () => {
      order.push('activate')
      return { id: 'draft-m', status: 'active' }
    })
    await openDraftM()

    fireEvent.change(screen.getByPlaceholderText('Election title'), {
      target: { value: 'Published Title' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    // The latest form state is saved first, so activation publishes what is on screen.
    expect(order).toEqual(['update', 'activate'])
    expect(updateElection).toHaveBeenCalledWith(
      'draft-m',
      expect.objectContaining({ title: 'Published Title' }),
    )
    expect(activateElection).toHaveBeenCalledWith('draft-m')
    expect(createElection).not.toHaveBeenCalled()
    expect(createElectionDraft).not.toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/election-detail', {
      state: { electionId: 'draft-m', from: 'active', role: 'organizer' },
    })
  })
})
