import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { loginUser, decodeJwt } from '../utils/api.js'

function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()

    try {
      const response = await loginUser(email, password)
      const token = response.access_token

      if (!token) {
        alert('Login failed: invalid response from server.')
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
        alert('Login succeeded, but user role is not recognized.')
      }
    } catch (error) {
      alert(error.message || 'Login failed. Please check your email and password.')
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-2xl rounded-sm border-2 border-slate-500 bg-slate-800/80 px-8 py-10 shadow-lg sm:px-14">
        <div className="mb-10 text-center">
          <h1 className="text-4xl font-semibold tracking-wide text-slate-100">Login</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-7">
          <div>
            <label htmlFor="email" className="mb-3 block text-xl font-medium text-slate-100">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="block h-14 w-full rounded-none border-2 border-slate-500 bg-slate-900/70 px-4 text-slate-100 outline-none transition focus:border-blue-400"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-3 block text-xl font-medium text-slate-100">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="block h-14 w-full rounded-none border-2 border-slate-500 bg-slate-900/70 px-4 text-slate-100 outline-none transition focus:border-blue-400"
            />
          </div>

          <div className="flex items-center justify-between gap-4 pt-8">
            <button
              type="submit"
              className="min-w-36 border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-lg font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300"
            >
              Login
            </button>

            <Link
              to="/register"
              className="min-w-36 border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-center text-lg font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300"
            >
              Sign up
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}

export default Login
