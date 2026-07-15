import { Link } from 'react-router-dom'

const NAV_LINKS = [
  { href: '#about', label: 'About' },
  { href: '#privacy', label: 'Privacy' },
  { href: '#features', label: 'Features' },
  { href: '#roles', label: 'Roles' },
  { href: '#technology', label: 'Technology' },
  { href: '#team', label: 'Team' },
]

const ABOUT_CARDS = [
  {
    title: 'Project Goal',
    body: 'Provide a secure and accessible voting system that improves voter privacy, vote integrity, and election management.',
  },
  {
    title: 'Target Environment',
    body: 'Built for academic institutions — classrooms, schools, universities, and student organizations — and the teachers, students, and administrators who run their elections.',
  },
  {
    title: 'Security Focus',
    body: 'Every ballot is encrypted before it is stored, and votes are counted without ever revealing an individual voter’s choice.',
  },
]

const PRIVACY_STEPS = [
  {
    title: '1. Encrypt',
    body: 'Your selection is encrypted the moment you submit it. The plaintext choice is never written to the database.',
  },
  {
    title: '2. Store ciphertext',
    body: 'Ballots are stored only as encrypted values, so someone reading the database cannot tell who voted for whom.',
  },
  {
    title: '3. Tally while encrypted',
    body: 'Homomorphic encryption lets the system add encrypted votes together without decrypting a single ballot.',
  },
  {
    title: '4. Publish totals only',
    body: 'Only the final per-candidate totals are decrypted. Individual votes are never revealed — not even to the organizer.',
  },
]

const FEATURES = [
  {
    title: 'Encrypted Vote Casting',
    body: 'Voters cast their ballots securely, with each vote encrypted before it is stored.',
  },
  {
    title: 'Duplicate Vote Prevention',
    body: 'Each eligible voter can cast exactly one ballot per election, enforced by the system.',
  },
  {
    title: 'Election Management',
    body: 'Organizers create elections, manage eligible voters, save drafts, and view results once an election ends.',
  },
  {
    title: 'User Account Management',
    body: 'System administrators can view, search, suspend, and unsuspend voter and organizer accounts.',
  },
]

// The academic framing is kept alongside the role names the application itself
// uses at registration and login, so the landing page matches what a visitor
// actually sees once they sign in.
const ROLES = [
  {
    title: 'Voter (Student)',
    items: [
      'Log in and view eligible active elections',
      'Cast encrypted votes',
      'View election and vote history',
    ],
  },
  {
    title: 'Organizer (Teacher)',
    items: [
      'Create and manage elections',
      'Save election drafts',
      'View active elections and completed results',
    ],
  },
  {
    title: 'System Admin',
    items: [
      'Manage voter and organizer accounts',
      'Search user account lists',
      'Suspend and unsuspend users',
    ],
  },
]

const TECHNOLOGIES = [
  'React',
  'JavaScript',
  'Python',
  'FastAPI',
  'Supabase',
  'PostgreSQL',
  'Homomorphic Encryption',
]

const TEAM = [
  {
    name: 'Wong Chong Yu Colin',
    role: 'Project Leader, Developer, Documentation',
    body: 'Monitors and delegates tasks to team members, assists with documentation, and supports the main coders in system development.',
  },
  {
    name: 'Teddy Kwok',
    role: 'Lead Developer, Product Testing, Frontend Developer',
    body: 'Second main coder focusing on frontend development and initial functionality testing before formal test case execution.',
  },
  {
    name: 'Lin HaiFeng',
    role: 'Lead Tester, Diagrams in Documentation, Developer',
    body: 'Main tester responsible for test cases and product testing, while also assisting with diagrams and development work.',
  },
  {
    name: 'Sun Ji',
    role: 'Lead Documentator, Developer',
    body: 'Main documentation lead responsible for preparing project documentation and supporting development tasks when needed.',
  },
  {
    name: 'Merrick',
    role: 'Lead Developer, Frontend and Backend Developer, Database Engineer',
    body: 'Main coder responsible for designing and developing the frontend, backend, and database structure of the system.',
  },
]

// Defined at module level: creating these during render would remount them on
// every update.
function Section({ id, title, intro, children }) {
  return (
    <section id={id} className="scroll-mt-24 px-4 py-14 sm:py-16">
      <div className="mx-auto max-w-5xl">
        <h2 className="text-center text-2xl font-semibold text-slate-100 sm:text-3xl">{title}</h2>
        {intro && (
          <p className="mx-auto mt-4 max-w-3xl text-center text-sm text-slate-300 sm:text-base">
            {intro}
          </p>
        )}
        <div className="mt-8">{children}</div>
      </div>
    </section>
  )
}

function Card({ title, children }) {
  return (
    <div className="rounded-2xl border border-slate-600 bg-slate-800/80 p-6 shadow-lg transition hover:border-blue-400">
      <h3 className="text-lg font-semibold text-blue-300">{title}</h3>
      <div className="mt-3 text-sm text-slate-300">{children}</div>
    </div>
  )
}

function Landing() {
  return (
    <div className="min-h-screen scroll-smooth bg-slate-900">
      {/* Hero */}
      <header className="border-b border-slate-700 bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 px-4 py-16 text-center sm:py-20">
        <div className="mx-auto max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-400">
            CSIT321 Final Year Project
          </p>
          <h1 className="mt-4 text-3xl font-semibold tracking-wide text-slate-100 sm:text-4xl">
            Homomorphic Encryption E-Voting System
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-sm text-slate-300 sm:text-base">
            A secure, mobile-friendly voting platform for teachers and students. Votes are tallied
            while they remain encrypted, so results are published without ever exposing an
            individual voter’s choice.
          </p>

          <div className="mt-9 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              to="/login"
              className="w-full rounded-2xl bg-blue-600 px-8 py-3 text-base font-semibold text-white transition hover:bg-blue-700 sm:w-auto"
            >
              Get Started
            </Link>
            <a
              href="#about"
              className="w-full rounded-2xl border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-base font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300 sm:w-auto"
            >
              Learn More
            </a>
          </div>
        </div>
      </header>

      {/* Section nav */}
      <nav className="sticky top-0 z-10 border-b border-slate-700 bg-slate-900/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-center gap-x-5 gap-y-2 sm:justify-between">
          <div className="flex flex-wrap justify-center gap-x-5 gap-y-2">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm font-medium text-slate-300 transition hover:text-blue-300"
              >
                {link.label}
              </a>
            ))}
          </div>
          <Link
            to="/login"
            className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700"
          >
            Login
          </Link>
        </div>
      </nav>

      <Section
        id="about"
        title="About The Project"
        intro="This project develops a practical e-voting system for educational environments such as classrooms, schools, universities, and student organizations. It uses homomorphic encryption to support secure vote tallying without exposing individual voter choices."
      >
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {ABOUT_CARDS.map((card) => (
            <Card key={card.title} title={card.title}>
              {card.body}
            </Card>
          ))}
        </div>
      </Section>

      <Section
        id="privacy"
        title="How Homomorphic Encryption Protects Your Vote"
        intro="Homomorphic encryption allows mathematics to be performed directly on encrypted data. That means the system can count an election without ever being able to read a single ballot."
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PRIVACY_STEPS.map((step) => (
            <div
              key={step.title}
              className="rounded-2xl border-l-4 border-blue-500 bg-slate-800/80 p-5 shadow-lg"
            >
              <h3 className="text-sm font-semibold text-blue-300">{step.title}</h3>
              <p className="mt-2 text-sm text-slate-300">{step.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section
        id="features"
        title="Main Features"
        intro="The system provides role-based features for managing users, creating elections, casting votes, and viewing results."
      >
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {FEATURES.map((feature) => (
            <Card key={feature.title} title={feature.title}>
              {feature.body}
            </Card>
          ))}
        </div>
      </Section>

      <Section id="roles" title="User Roles">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {ROLES.map((role) => (
            <Card key={role.title} title={role.title}>
              <ul className="list-disc space-y-1 pl-5">
                {role.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      </Section>

      <Section
        id="technology"
        title="Technology Stack"
        intro="The project uses a modern web stack supporting a responsive interface, structured backend APIs, reliable data storage, and encryption-related functionality."
      >
        <div className="flex flex-wrap justify-center gap-3">
          {TECHNOLOGIES.map((tech) => (
            <span
              key={tech}
              className="rounded-full border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-semibold text-blue-300"
            >
              {tech}
            </span>
          ))}
        </div>
      </Section>

      <Section
        id="team"
        title="Project Team"
        intro="Developed by a team of students with assigned roles across project management, frontend and backend development, database design, testing, documentation, and system diagrams."
      >
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {TEAM.map((member) => (
            <Card key={member.name} title={member.name}>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                {member.role}
              </p>
              <p className="mt-2">{member.body}</p>
            </Card>
          ))}
        </div>
      </Section>

      {/* Closing call to action */}
      <section className="px-4 pb-16">
        <div className="mx-auto max-w-3xl rounded-2xl border border-slate-600 bg-slate-800/80 px-6 py-10 text-center shadow-lg">
          <h2 className="text-xl font-semibold text-slate-100 sm:text-2xl">Ready to vote securely?</h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-slate-300">
            Sign in to view your eligible elections, or create an account to get started.
          </p>
          <div className="mt-7 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              to="/login"
              className="w-full rounded-2xl bg-blue-600 px-8 py-3 text-base font-semibold text-white transition hover:bg-blue-700 sm:w-auto"
            >
              Login
            </Link>
            <Link
              to="/register"
              className="w-full rounded-2xl border-2 border-slate-500 bg-slate-900/70 px-8 py-3 text-base font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300 sm:w-auto"
            >
              Create Account
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-700 bg-slate-950 px-4 py-8 text-center">
        <p className="text-sm font-semibold text-slate-200">CSIT321 Final Year Project</p>
        <p className="mt-1 text-sm text-slate-400">
          Homomorphic Encryption and its Applications to E-Voting
        </p>
      </footer>
    </div>
  )
}

export default Landing
