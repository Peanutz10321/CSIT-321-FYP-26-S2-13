import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { loginUser, decodeJwt } from '../utils/api.js'

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

function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')

    try {
      const response = await loginUser(email, password)
      const token = response.access_token

      if (!token) {
        setError('Login failed: invalid response from server.')
        return
      }

      localStorage.setItem('authToken', token)
      const payload = decodeJwt(token)
      const role = payload?.role

      if (role === 'voter') {
        navigate('/voter-dashboard')
      } else if (role === 'organizer') {
        navigate('/organizer-dashboard')
      } else if (role === 'system_admin') {
        navigate('/admin-dashboard')
      } else {
        setError('Login succeeded, but user role is not recognized.')
      }
    } catch (err) {
      setError(err.message || 'Login failed. Please check your email and password.')
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
            Secure Sign In
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
            Welcome back
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            Sign in to view your elections and cast your vote.
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
              <label htmlFor="email" className={labelClass}>
                Email
              </label>
              <input
                id="email"
                name="email"
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
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                className={inputClass}
              />
            </div>

            <button type="submit" className={`${primaryButtonClass} mt-2`}>
              Login
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-sm text-slate-400">
          Don&apos;t have an account?{' '}
          <Link to="/register" className="font-semibold text-blue-400 hover:text-blue-300">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  )
}

export default Login
