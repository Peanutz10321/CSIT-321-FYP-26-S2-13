import { Link } from 'react-router-dom'

const NAV_LINKS = [
  { href: '#about', label: 'About' },
  { href: '#privacy', label: 'Privacy' },
  { href: '#features', label: 'Features' },
  { href: '#roles', label: 'Roles' },
  { href: '#technology', label: 'Technology' },
  { href: '#team', label: 'Team' },
]

const TRUST_POINTS = [
  { title: 'Encrypted ballots', body: 'Each vote is encrypted before it is stored.' },
  { title: 'One vote per voter', body: 'Eligibility and duplicate votes are enforced.' },
  { title: 'Tally without decryption', body: 'Only final totals are ever revealed.' },
]

const ABOUT_CARDS = [
  {
    title: 'Project Goal',
    body: 'Provide a secure and accessible voting system that improves voter privacy, vote integrity, and election management.',
  },
  {
    title: 'Target Environment',
    body: 'Built for academic institutions and organizations — and the voters, organizers, and administrators who run their elections.',
  },
  {
    title: 'Security Focus',
    body: 'Every ballot is encrypted before it is stored, and votes are aggregated without decrypting individual ballots during normal tallying.',
  },
]

const PRIVACY_STEPS = [
  {
    step: '01',
    title: 'Encrypt',
    body: 'Your selection is encrypted the moment you submit it. The plaintext choice is never written to the database.',
  },
  {
    step: '02',
    title: 'Store ciphertext',
    body: 'Ballots are stored only as encrypted values, so someone reading the database cannot tell who voted for whom.',
  },
  {
    step: '03',
    title: 'Tally while encrypted',
    body: 'Homomorphic encryption lets the system add encrypted votes together without decrypting a single ballot.',
  },
  {
    step: '04',
    title: 'Publish totals only',
    body: 'Only the final per-candidate totals are decrypted. Individual ballots are not decrypted during the normal tally process.',
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

const ROLES = [
  {
    title: 'Voter',
    tone: 'blue',
    items: [
      'Log in and view eligible active elections',
      'Cast encrypted votes',
      'View election and vote history',
    ],
  },
  {
    title: 'Organizer',
    tone: 'amber',
    items: [
      'Create and manage elections',
      'Save election drafts',
      'View active elections and completed results',
    ],
  },
  {
    title: 'System Admin',
    tone: 'rose',
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

const ROLE_ACCENT = {
  blue: 'text-blue-300 ring-blue-500/30',
  amber: 'text-amber-300 ring-amber-500/30',
  rose: 'text-rose-300 ring-rose-500/30',
}

// Inline SVGs — no external assets or dependencies.
function LockIcon({ className = 'h-4 w-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
    </svg>
  )
}

function CheckIcon({ className = 'h-4 w-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
      <path d="M4 12.5l5 5 11-11" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// Defined at module level: creating these during render would remount them.
function Section({ id, title, intro, children }) {
  return (
    <section id={id} className="scroll-mt-20 px-4 py-16 sm:py-20">
      <div className="mx-auto max-w-5xl">
        <h2 className="text-center text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
          {title}
        </h2>
        {intro && (
          <p className="mx-auto mt-4 max-w-3xl text-center text-sm leading-relaxed text-slate-400 sm:text-base">
            {intro}
          </p>
        )}
        <div className="mt-10">{children}</div>
      </div>
    </section>
  )
}

function Card({ title, children }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-lg shadow-slate-950/40 transition hover:border-blue-500/50 hover:bg-slate-900">
      <h3 className="text-base font-semibold text-blue-300">{title}</h3>
      <div className="mt-3 text-sm leading-relaxed text-slate-400">{children}</div>
    </div>
  )
}

function BallotPreview() {
  const options = [
    { name: 'Alice Tan', selected: true },
    { name: 'Bob Lee', selected: false },
    { name: 'Priya Nair', selected: false },
  ]
  return (
    <div
      className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-2xl shadow-blue-950/40 backdrop-blur"
      aria-hidden="true"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-blue-400">Ballot</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-100">Class Representative</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300">
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          Open
        </span>
      </div>

      <div className="mt-4 space-y-2">
        {options.map((option) => (
          <div
            key={option.name}
            className={`flex items-center gap-3 rounded-xl border px-3.5 py-2.5 text-sm ${
              option.selected
                ? 'border-blue-500/60 bg-blue-500/10 text-slate-100'
                : 'border-slate-800 bg-slate-950/40 text-slate-300'
            }`}
          >
            <span
              className={`flex h-4 w-4 items-center justify-center rounded-full border ${
                option.selected ? 'border-blue-400 bg-blue-500' : 'border-slate-600'
              }`}
            >
              {option.selected && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
            </span>
            {option.name}
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2 border-t border-slate-800 pt-3 text-[11px] text-slate-400">
        <LockIcon className="h-3.5 w-3.5 text-emerald-400" />
        Encrypted on submit · tallied without decryption
      </div>
    </div>
  )
}

function Landing() {
  return (
    <div className="min-h-screen scroll-smooth bg-slate-950 text-slate-100">
      {/* Sticky nav */}
      <nav className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <span className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600/20 text-blue-300 ring-1 ring-blue-500/30">
              <LockIcon className="h-4 w-4" />
            </span>
            HE E-Voting
          </span>
          <div className="hidden flex-wrap items-center gap-x-6 gap-y-1 md:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm font-medium text-slate-400 transition hover:text-blue-300"
              >
                {link.label}
              </a>
            ))}
          </div>
          <Link
            to="/login"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-500"
          >
            Login
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <header className="relative overflow-hidden border-b border-slate-800 bg-slate-950">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(37,99,235,0.18),transparent_70%)]" />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(148,163,184,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(148,163,184,0.05)_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]" />

        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:py-20 lg:grid-cols-[1.1fr_0.9fr] lg:py-24">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-blue-300">
              <LockIcon className="h-3.5 w-3.5" />
              CSIT321 Final Year Project
            </span>
            <h1 className="mt-5 text-4xl font-semibold leading-tight tracking-tight text-slate-100 sm:text-5xl">
              Homomorphic Encryption E-Voting System
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-400">
              A secure, mobile-friendly voting platform for voters and organizers. Votes are tallied
              while they remain encrypted, so results are published without decrypting individual
              ballots during normal tallying.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                to="/login"
                className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-7 py-3 text-base font-semibold text-white transition hover:bg-blue-500"
              >
                Get Started
              </Link>
              <a
                href="#privacy"
                className="inline-flex items-center justify-center rounded-xl border border-slate-700 bg-slate-900/60 px-7 py-3 text-base font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300"
              >
                See how it works
              </a>
            </div>

            <dl className="mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-slate-800 pt-6">
              {TRUST_POINTS.map((point) => (
                <div key={point.title}>
                  <dt className="flex items-center gap-1.5 text-sm font-semibold text-slate-100">
                    <CheckIcon className="h-4 w-4 text-emerald-400" />
                    {point.title}
                  </dt>
                  <dd className="mt-1 text-xs leading-relaxed text-slate-500">{point.body}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="flex justify-center lg:justify-end">
            <BallotPreview />
          </div>
        </div>
      </header>

      <Section
        id="about"
        title="About The Project"
        intro="This project develops a practical e-voting system for educational environments and organizations. It uses homomorphic encryption so encrypted ballots are aggregated before tally decryption."
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
        intro="Homomorphic encryption allows mathematics to be performed directly on encrypted data. That means the system can count an election while individual ballots stay encrypted during the normal tally process."
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PRIVACY_STEPS.map((step) => (
            <div
              key={step.step}
              className="relative rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg shadow-slate-950/40"
            >
              <span className="text-2xl font-bold tracking-tight text-slate-700">{step.step}</span>
              <h3 className="mt-1 text-sm font-semibold text-blue-300">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{step.body}</p>
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
            <div
              key={role.title}
              className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-lg shadow-slate-950/40"
            >
              <h3
                className={`inline-flex items-center rounded-lg px-2.5 py-1 text-base font-semibold ring-1 ${
                  ROLE_ACCENT[role.tone] ?? ROLE_ACCENT.blue
                }`}
              >
                {role.title}
              </h3>
              <ul className="mt-4 space-y-2.5">
                {role.items.map((item) => (
                  <li key={item} className="flex items-start gap-2.5 text-sm leading-relaxed text-slate-300">
                    <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
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
              className="rounded-full border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-semibold text-blue-300"
            >
              {tech}
            </span>
          ))}
        </div>
      </Section>

      <Section
        id="team"
        title="Project Team"
        intro="Developed by a five-person project team with assigned roles across project management, frontend and backend development, database design, testing, documentation, and system diagrams."
      >
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {TEAM.map((member) => (
            <Card key={member.name} title={member.name}>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {member.role}
              </p>
              <p className="mt-2 text-slate-400">{member.body}</p>
            </Card>
          ))}
        </div>
      </Section>

      {/* Closing call to action */}
      <section className="px-4 pb-20">
        <div className="relative mx-auto max-w-4xl overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/70 px-6 py-12 text-center shadow-2xl shadow-blue-950/30">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(37,99,235,0.12),transparent_70%)]" />
          <div className="relative">
            <h2 className="text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">
              Ready to vote securely?
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-slate-400">
              Sign in to view your eligible elections, or create an account to get started.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                to="/login"
                className="w-full rounded-xl bg-blue-600 px-8 py-3 text-base font-semibold text-white transition hover:bg-blue-500 sm:w-auto"
              >
                Login
              </Link>
              <Link
                to="/register"
                className="w-full rounded-xl border border-slate-700 bg-slate-950/40 px-8 py-3 text-base font-medium text-slate-100 transition hover:border-blue-400 hover:text-blue-300 sm:w-auto"
              >
                Create Account
              </Link>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-800 bg-slate-950 px-4 py-10 text-center">
        <p className="flex items-center justify-center gap-2 text-sm font-semibold text-slate-200">
          <LockIcon className="h-4 w-4 text-blue-400" />
          CSIT321 Final Year Project
        </p>
        <p className="mt-1.5 text-sm text-slate-500">
          Homomorphic Encryption and its Applications to E-Voting
        </p>
      </footer>
    </div>
  )
}

export default Landing
