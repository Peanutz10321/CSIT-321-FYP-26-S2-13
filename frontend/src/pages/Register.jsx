import { Link } from 'react-router-dom'

function Register() {
  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md bg-slate-800 border border-slate-700 rounded-3xl shadow-sm p-8">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-semibold text-slate-100">Create Account</h1>
          <p className="mt-2 text-sm text-slate-400">Register to join the voting platform</p>
        </div>

        <form className="space-y-6">
          <div>
            <label htmlFor="role" className="block text-sm font-medium text-slate-300">
              Role
            </label>
            <select
              id="role"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            >
              <option>Student</option>
              <option>Teacher</option>
            </select>
          </div>

          <div>
            <label htmlFor="name" className="block text-sm font-medium text-slate-300">
              Name
            </label>
            <input
              id="name"
              type="text"
              placeholder="Enter your name"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-300">
              Email
            </label>
            <input
              id="email"
              type="email"
              placeholder="Enter your email"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-300">
              Password
            </label>
            <input
              id="password"
              type="password"
              placeholder="Create a password"
              className="mt-2 block w-full rounded-2xl border border-slate-600 bg-slate-700 px-4 py-3 text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-800"
            />
          </div>

          <button
            type="submit"
            className="w-full rounded-2xl bg-blue-600 px-4 py-3 text-white font-semibold shadow-sm transition hover:bg-blue-700"
          >
            Register
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
