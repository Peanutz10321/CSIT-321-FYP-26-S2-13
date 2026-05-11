import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { registerUser } from '../utils/api.js'

function Register() {
  const navigate = useNavigate()
  const [role, setRole] = useState('student')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()

    if (!username.trim()) {
      alert('Please enter a username.')
      return
    }
    if (!email.trim()) {
      alert('Please enter your email.')
      return
    }
    if (!password) {
      alert('Please enter a password.')
      return
    }

    setSubmitting(true)

    try {
      const payload = {
        username: username.trim(),
        email: email.trim(),
        password,
        role,
      }

      await registerUser(payload)
      alert('Account created successfully! Please login.')
      navigate('/login')
    } catch (error) {
      alert(`Registration failed: ${error.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-xl rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg sm:px-12">
        <div className="mb-10 text-center">
          <h1 className="text-4xl font-semibold tracking-wide text-slate-100">Register Account</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-7">
          <div>
            <label htmlFor="username" className="mb-3 block text-xl font-medium text-slate-100">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="block h-14 w-full rounded-none border-2 border-slate-500 bg-slate-900/70 px-4 text-slate-100 outline-none transition focus:border-blue-400"
              required
            />
          </div>

          <div>
            <label htmlFor="email" className="mb-3 block text-xl font-medium text-slate-100">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="block h-14 w-full rounded-none border-2 border-slate-500 bg-slate-900/70 px-4 text-slate-100 outline-none transition focus:border-blue-400"
              required
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-3 block text-xl font-medium text-slate-100">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="block h-14 w-full rounded-none border-2 border-slate-500 bg-slate-900/70 px-4 text-slate-100 outline-none transition focus:border-blue-400"
              required
            />
          </div>

          <div>
            <label htmlFor="role" className="mb-3 block text-xl font-medium text-slate-100">
              Profile
            </label>
            <select
              id="role"
              value={role}
              onChange={(event) => setRole(event.target.value)}
              className="block h-14 w-full rounded-none border-2 border-slate-500 bg-slate-900/70 px-4 text-slate-100 outline-none transition focus:border-blue-400"
            >
              <option value="student">Student</option>
              <option value="teacher">Teacher</option>
            </select>
          </div>

          <div className="flex items-center justify-center gap-4 pt-5">
            <button
              type="submit"
              disabled={submitting}
              className="border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-lg font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? 'Registering...' : 'Register'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default Register
