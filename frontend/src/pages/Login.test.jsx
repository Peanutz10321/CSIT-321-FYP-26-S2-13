import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import Login from './Login.jsx'
import { loginUser, decodeJwt } from '../utils/api.js'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../utils/api.js', () => ({
  loginUser: vi.fn(),
  decodeJwt: vi.fn(),
}))

function renderLogin() {
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  )
}

async function submitLoginAs(role) {
  loginUser.mockResolvedValue({ access_token: 'fake.jwt.token' })
  decodeJwt.mockReturnValue({ role })

  renderLogin()
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'x@test.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
  fireEvent.click(screen.getByRole('button', { name: 'Login' }))
}

describe('Login redirects by new role', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends a voter to the voter dashboard', async () => {
    await submitLoginAs('voter')
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/voter-dashboard'))
  })

  it('sends an organizer to the organizer dashboard', async () => {
    await submitLoginAs('organizer')
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/organizer-dashboard'))
  })

  it('sends a system admin to the admin dashboard', async () => {
    await submitLoginAs('system_admin')
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/admin-dashboard'))
  })

  it('never navigates to the old school-specific routes', async () => {
    await submitLoginAs('voter')
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(navigateMock).not.toHaveBeenCalledWith('/student-dashboard')
    expect(navigateMock).not.toHaveBeenCalledWith('/teacher-dashboard')
  })
})

describe('Login rejects incomplete credentials', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows one message for a blank email, without calling the API', async () => {
    renderLogin()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Login' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Please provide a valid email and password.',
    )
    expect(loginUser).not.toHaveBeenCalled()
  })

  it('shows the same message for a blank password', async () => {
    renderLogin()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'x@test.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Login' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Please provide a valid email and password.',
    )
    expect(loginUser).not.toHaveBeenCalled()
  })

  it('replaces the raw validator text when the backend rejects the address', async () => {
    // An address the browser accepts but the backend's EmailStr does not.
    const rejected = new Error('value is not a valid email address: The part after the @-sign is not valid.')
    rejected.status = 422
    loginUser.mockRejectedValue(rejected)

    renderLogin()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Login' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Please provide a valid email and password.',
    )
  })

  it('still surfaces the server message for a failed credential check', async () => {
    const rejected = new Error('Invalid email or password')
    rejected.status = 401
    loginUser.mockRejectedValue(rejected)

    renderLogin()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'x@test.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Login' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
  })
})
