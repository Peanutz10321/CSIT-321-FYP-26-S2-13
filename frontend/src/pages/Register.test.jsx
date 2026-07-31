import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import Register from './Register.jsx'
import { registerUser, loginUser, decodeJwt } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  registerUser: vi.fn(),
  loginUser: vi.fn(),
  decodeJwt: vi.fn(),
}))

function renderRegister() {
  render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>,
  )
}

function fillCredentials() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'newuser' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@test.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw123456' } })
}

function selectRole(name) {
  fireEvent.change(screen.getByLabelText('Register as'), { target: { value: name } })
}

describe('Register role selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('offers Voter and Organizer options', () => {
    renderRegister()
    expect(screen.getByRole('option', { name: 'Voter' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Organizer' })).toBeInTheDocument()
  })

  it('never offers a System Admin option', () => {
    renderRegister()
    expect(screen.queryByRole('option', { name: /system admin/i })).not.toBeInTheDocument()
  })

  it('defaults to the voter role', () => {
    renderRegister()
    expect(screen.getByLabelText('Register as')).toHaveValue('voter')
  })

  it('enforces and explains the backend password minimum', () => {
    renderRegister()

    expect(screen.getByLabelText('Password')).toHaveAttribute('minlength', '8')
    expect(screen.getByText(/password must be at least 8 characters/i)).toBeInTheDocument()
  })
})

describe('Register submit flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    registerUser.mockResolvedValue({})
    loginUser.mockResolvedValue({ access_token: 'fake.jwt.token' })
  })

  it('registers a voter and redirects to the voter dashboard', async () => {
    decodeJwt.mockReturnValue({ role: 'voter' })

    renderRegister()
    fillCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() =>
      expect(registerUser).toHaveBeenCalledWith(expect.objectContaining({ role: 'voter' })),
    )
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/voter-dashboard'))
  })

  it('submits the organizer role and redirects to the organizer dashboard', async () => {
    decodeJwt.mockReturnValue({ role: 'organizer' })

    renderRegister()
    fillCredentials()
    selectRole('organizer')
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() =>
      expect(registerUser).toHaveBeenCalledWith(
        expect.objectContaining({ role: 'organizer' }),
      ),
    )
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/organizer-dashboard'))
  })

  it('submits the exact role the user selected', async () => {
    decodeJwt.mockReturnValue({ role: 'organizer' })

    renderRegister()
    fillCredentials()
    selectRole('organizer')
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() => expect(registerUser).toHaveBeenCalled())

    const payload = registerUser.mock.calls[0][0]
    expect(payload.role).toBe('organizer')
  })
})

describe('Register organization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    decodeJwt.mockReturnValue({ role: 'voter' })
    loginUser.mockResolvedValue({ access_token: 'token' })
    registerUser.mockResolvedValue({ id: 'u1' })
  })

  it('submits the organization the user typed', async () => {
    renderRegister()
    fillCredentials()
    fireEvent.change(screen.getByLabelText(/Organization/), {
      target: { value: 'Engineering Club' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() =>
      expect(registerUser).toHaveBeenCalledWith(
        expect.objectContaining({ group: 'Engineering Club' }),
      ),
    )
  })

  it('limits the organization field to the 50-character column width', () => {
    renderRegister()

    // Matches String(GROUP_MAX_LENGTH) on the model and the schema's max_length,
    // so the form cannot compose a value the backend will reject with a 422.
    expect(screen.getByLabelText(/Organization/)).toHaveAttribute('maxlength', '50')
  })

  it('submits a 50-character organization unchanged', async () => {
    const name = 'G'.repeat(50)
    renderRegister()
    fillCredentials()
    fireEvent.change(screen.getByLabelText(/Organization/), { target: { value: name } })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() =>
      expect(registerUser).toHaveBeenCalledWith(expect.objectContaining({ group: name })),
    )
  })

  it('trims surrounding whitespace from the organization', async () => {
    renderRegister()
    fillCredentials()
    fireEvent.change(screen.getByLabelText(/Organization/), {
      target: { value: '  Engineering Club  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() =>
      expect(registerUser).toHaveBeenCalledWith(
        expect.objectContaining({ group: 'Engineering Club' }),
      ),
    )
  })

  it('omits the field entirely when only whitespace is given', async () => {
    renderRegister()
    fillCredentials()
    fireEvent.change(screen.getByLabelText(/Organization/), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() => expect(registerUser).toHaveBeenCalled())
    expect(registerUser.mock.calls[0][0]).not.toHaveProperty('group')
  })

  it('omits the field entirely when no organization is given', async () => {
    renderRegister()
    fillCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    await waitFor(() => expect(registerUser).toHaveBeenCalled())
    // Absent rather than "": the column is nullable and blank is not a group.
    expect(registerUser.mock.calls[0][0]).not.toHaveProperty('group')
  })
})
