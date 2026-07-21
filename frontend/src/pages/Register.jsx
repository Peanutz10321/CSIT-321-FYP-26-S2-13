import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { registerUser, loginUser, decodeJwt } from '../utils/api.js'

// Inline lock SVG so the auth pages stay self-contained and match the landing brand.
function LockIcon({ className = 'h-4 w-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
    </svg>
  )
}

const inputClass =
  'block w-full rounded-lg border border-slate-700 bg-slate-950/60 px-4 py-2.5 text-slate-100 placeholder-slate-500 transition focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40'
const labelClass = 'mb-2 block text-sm font-medium text-slate-200'
const primaryButtonClass =
  'inline-flex w-full items-center justify-center rounded-xl bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:cursor-not-allowed disabled:opacity-60'

function Register() {
  const navigate = useNavigate()
  const [role, setRole] = useState('voter')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')

    try {
      const payload = {
        username: username.trim(),
        email: email.trim(),
        password,
        role,
      }

      await registerUser(payload)

      const loginResponse = await loginUser(email.trim(), password)
      const token = loginResponse.access_token
      localStorage.setItem('authToken', token)
      const decoded = decodeJwt(token)
      const userRole = decoded?.role

      if (userRole === 'voter') {
        navigate('/voter-dashboard')
      } else if (userRole === 'organizer') {
        navigate('/organizer-dashboard')
      } else {
        navigate('/login')
      }
    } catch (err) {
      setError(err.message || 'Registration failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-12 text-slate-100">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(37,99,235,0.16),transparent_70%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(148,163,184,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(148,163,184,0.05)_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_40%,black,transparent)]" />

      <div className="relative w-full max-w-md">
        <Link to="/" className="mb-8 flex items-center justify-center gap-2 text-sm font-semibold text-slate-100">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600/20 text-blue-300 ring-1 ring-blue-500/30">
            <LockIcon className="h-4 w-4" />
          </span>
          HE E-Voting
        </Link>

        <div className="text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-blue-300">
            <LockIcon className="h-3.5 w-3.5" />
            Create Account
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
            Create your account
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            Register as a voter or an election organizer.
          </p>
        </div>

        <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-2xl shadow-slate-950/50 sm:p-8">
          {error && (
            <div
              role="alert"
              className="mb-5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="username" className={labelClass}>
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Choose a username"
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="email" className={labelClass}>
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="password" className={labelClass}>
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Create a password"
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="role" className={labelClass}>
                Profile
              </label>
              <select
                id="role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
                className={inputClass}
              >
                <option value="voter">Voter</option>
                <option value="organizer">Organizer</option>
              </select>
              <p className="mt-1.5 text-xs text-slate-500">
                Choose how you&apos;ll use the system. Organizers can create and manage elections.
              </p>
            </div>

            <button type="submit" disabled={submitting} className={`${primaryButtonClass} mt-2`}>
              {submitting ? 'Registering...' : 'Register'}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-sm text-slate-400">
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-blue-400 hover:text-blue-300">
            Log in
          </Link>
        </p>
      </div>
    </div>
  )
}

export default Register
