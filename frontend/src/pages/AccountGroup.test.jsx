import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import ViewAccount from './ViewAccount.jsx'
import UpdateAccount from './UpdateAccount.jsx'
import { getCurrentUser, updateCurrentUser } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock, useLocation: () => ({ state: {} }) }
})

vi.mock('../utils/api.js', () => ({
  getCurrentUser: vi.fn(),
  updateCurrentUser: vi.fn(),
}))

function account(overrides = {}) {
  return {
    id: 'u1',
    role: 'voter',
    status: 'active',
    external_id: 'VOTER-001',
    username: 'voter1',
    full_name: 'Voter One',
    email: 'voter1@test.com',
    group: 'Engineering Club',
    ...overrides,
  }
}

function renderPage(Page) {
  render(
    <MemoryRouter>
      <Page />
    </MemoryRouter>,
  )
}

const groupField = () => screen.getByLabelText(/Organization/)

describe('ViewAccount shows the organization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('authToken', 'token')
  })

  it('displays the group for a voter', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(ViewAccount)

    expect(await screen.findByText('Organization')).toBeInTheDocument()
    expect(screen.getByText('Engineering Club')).toBeInTheDocument()
  })

  it('displays the group for an organizer', async () => {
    getCurrentUser.mockResolvedValue(account({ role: 'organizer', group: 'Faculty Office' }))
    renderPage(ViewAccount)

    expect(await screen.findByText('Faculty Office')).toBeInTheDocument()
  })

  it('falls back to a dash when the account has no organization', async () => {
    getCurrentUser.mockResolvedValue(account({ group: null }))
    renderPage(ViewAccount)

    await screen.findByText('Organization')
    // The row is present but empty rather than missing, matching the other fields.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})

describe('UpdateAccount edits the organization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    updateCurrentUser.mockResolvedValue(account())
  })

  it('prefills the current organization', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(groupField()).toHaveValue('Engineering Club'))
  })

  it('is capped at the 50-character column width', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(groupField()).toBeInTheDocument())
    expect(groupField()).toHaveAttribute('maxlength', '50')
  })

  it('submits a changed organization', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(groupField()).toBeInTheDocument())
    fireEvent.change(groupField(), { target: { value: 'Chess Club' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(updateCurrentUser).toHaveBeenCalledWith(
        expect.objectContaining({ group: 'Chess Club' }),
      ),
    )
  })

  it('sends an empty string when the box is cleared, so the group is left', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(groupField()).toBeInTheDocument())
    fireEvent.change(groupField(), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(updateCurrentUser).toHaveBeenCalled())
    // Present and empty — omitting it would tell the backend "leave it alone".
    expect(updateCurrentUser.mock.calls[0][0]).toHaveProperty('group', '')
  })

  it('trims the organization before sending it', async () => {
    getCurrentUser.mockResolvedValue(account({ group: null }))
    renderPage(UpdateAccount)

    await waitFor(() => expect(groupField()).toBeInTheDocument())
    fireEvent.change(groupField(), { target: { value: '  Chess Club  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(updateCurrentUser).toHaveBeenCalledWith(
        expect.objectContaining({ group: 'Chess Club' }),
      ),
    )
  })

  it('advertises the same 8-character minimum as registration', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(screen.getByLabelText('New Password')).toBeInTheDocument())
    expect(screen.getByLabelText('New Password')).toHaveAttribute('minlength', '8')
  })

  it('blocks a too-short password before it reaches the backend', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(screen.getByLabelText('New Password')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('New Password'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith('Password must be at least 8 characters.'),
    )
    expect(updateCurrentUser).not.toHaveBeenCalled()
  })

  it('accepts a password at exactly the minimum', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(screen.getByLabelText('New Password')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('New Password'), { target: { value: '12345678' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(updateCurrentUser).toHaveBeenCalledWith(
        expect.objectContaining({ password: '12345678' }),
      ),
    )
  })

  it('omits the password entirely when the box is left blank', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(screen.getByLabelText('New Password')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(updateCurrentUser).toHaveBeenCalled())
    // Absent, so the backend keeps the current password rather than validating "".
    expect(updateCurrentUser.mock.calls[0][0]).not.toHaveProperty('password')
  })

  it('still sends the other account fields alongside the group', async () => {
    getCurrentUser.mockResolvedValue(account())
    renderPage(UpdateAccount)

    await waitFor(() => expect(groupField()).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(updateCurrentUser).toHaveBeenCalled())
    expect(updateCurrentUser.mock.calls[0][0]).toMatchObject({
      username: 'voter1',
      email: 'voter1@test.com',
      group: 'Engineering Club',
    })
  })
})

describe('UpdateAccount rejects a missing username or email', () => {
  const MESSAGE = 'Missing field or invalid input detected. Please key in again'
  const usernameField = () => screen.getByLabelText('Username')
  const emailField = () => screen.getByLabelText(/Email/)

  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    updateCurrentUser.mockResolvedValue(account())
    getCurrentUser.mockResolvedValue(account())
  })

  it('blocks a blank username before it reaches the backend', async () => {
    renderPage(UpdateAccount)

    await waitFor(() => expect(usernameField()).toHaveValue('voter1'))
    fireEvent.change(usernameField(), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith(MESSAGE))
    expect(updateCurrentUser).not.toHaveBeenCalled()
  })

  it('blocks a blank email', async () => {
    renderPage(UpdateAccount)

    await waitFor(() => expect(emailField()).toHaveValue('voter1@test.com'))
    fireEvent.change(emailField(), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith(MESSAGE))
    expect(updateCurrentUser).not.toHaveBeenCalled()
  })

  it('treats a whitespace-only username as blank', async () => {
    renderPage(UpdateAccount)

    await waitFor(() => expect(usernameField()).toHaveValue('voter1'))
    // min_length=1 on the backend counts spaces, so this would otherwise be stored.
    fireEvent.change(usernameField(), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith(MESSAGE))
    expect(updateCurrentUser).not.toHaveBeenCalled()
  })

  it('trims the username and email before sending them', async () => {
    renderPage(UpdateAccount)

    await waitFor(() => expect(usernameField()).toHaveValue('voter1'))
    fireEvent.change(usernameField(), { target: { value: '  voter2  ' } })
    fireEvent.change(emailField(), { target: { value: '  voter2@test.com  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(updateCurrentUser).toHaveBeenCalledWith(
        expect.objectContaining({ username: 'voter2', email: 'voter2@test.com' }),
      ),
    )
  })

  it('replaces the raw validator text when the backend rejects the email', async () => {
    // Save is a plain button outside a <form>, so type="email" never blocks this.
    const rejected = new Error('value is not a valid email address: An email address must have an @-sign.')
    rejected.status = 422
    updateCurrentUser.mockRejectedValue(rejected)
    renderPage(UpdateAccount)

    await waitFor(() => expect(emailField()).toHaveValue('voter1@test.com'))
    fireEvent.change(emailField(), { target: { value: 'not-an-email' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith(MESSAGE))
  })

  it('still reports other save failures with the server message', async () => {
    const rejected = new Error('Username already exists')
    rejected.status = 400
    updateCurrentUser.mockRejectedValue(rejected)
    renderPage(UpdateAccount)

    await waitFor(() => expect(usernameField()).toHaveValue('voter1'))
    fireEvent.change(usernameField(), { target: { value: 'taken' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith(
        'Failed to update account: Username already exists',
      ),
    )
  })
})
