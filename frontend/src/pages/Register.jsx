import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { registerUser } from '../utils/api.js'

function Register() {
  const navigate = useNavigate()
  const [role, setRole] = useState('student')
  const [institutionId, setInstitutionId] = useState('')
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    console.log('[Register] handleSubmit called')

    if (!institutionId.trim()) {
      alert('Please enter your Institution ID.')
      return
    }
    if (!username.trim()) {
      alert('Please enter a username.')
      return
    }
    if (!fullName.trim()) {
      alert('Please enter your full name.')
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
        institution_id: institutionId.trim(),
        username: username.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role,
      }

      console.log('[Register] Sending payload:', { ...payload, password: '***' })
      await registerUser(payload)
      console.log('[Register] Registration successful')

      alert('Account created successfully! Please login.')
      navigate('/login')
    } catch (error) {
      console.error('[Register] Registration error:', error)
      alert(`Registration failed: ${error.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md bg-slate-800 border border-slate-700 rounded-3xl shadow-sm p-8">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-semibold text-slate-100">Create Account</h1>
          <p className="mt-2 text-sm text-slate-400">Register to join the voting platform</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="role" className="block text-sm font-medium text-slate-300">
              Role
            </label>
            <select
              id="role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            >
              <option value="student">Student</option>
              <option value="teacher">Teacher</option>
            </select>
          </div>

          <div>
            <label htmlFor="institutionId" className="block text-sm font-medium text-slate-300">
              Institution ID
            </label>
            <input
              id="institutionId"
              type="text"
              value={institutionId}
              onChange={(e) => setInstitutionId(e.target.value)}
              placeholder="Enter your student/staff ID"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              required
            />
          </div>

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-slate-300">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Choose a username"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              required
            />
          </div>

          <div>
            <label htmlFor="fullName" className="block text-sm font-medium text-slate-300">
              Full Name
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Enter your full name"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              required
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-300">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              required
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-300">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Create a password"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
              required
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-2xl bg-blue-600 px-4 py-3 text-white font-semibold shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? 'Creating Account...' : 'Register'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-400">
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-blue-400 hover:text-blue-300">
            Login
          </Link>
        </p>
      </div>
    </div>
  )
}

export default Register
