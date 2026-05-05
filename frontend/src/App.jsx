import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Register from './pages/Register'
import StudentDashboard from './pages/StudentDashboard'
import TeacherDashboard from './pages/TeacherDashboard'
import AdminDashboard from './pages/AdminDashboard'
import ActiveElections from './pages/ActiveElections'
import CastVote from './pages/CastVote'
import VoteHistory from './pages/VoteHistory'
import VoteReceipt from './pages/VoteReceipt'
import CreateElection from './pages/CreateElection'
import ElectionDraft from './pages/ElectionDraft'
import UpdateElection from './pages/UpdateElection'
import ElectionHistory from './pages/ElectionHistory'
import ElectionResults from './pages/ElectionResults'
import ElectionDetail from './pages/ElectionDetail'
import ManageUsers from './pages/ManageUsers'
import ViewAccount from './pages/ViewAccount'
import UpdateAccount from './pages/UpdateAccount'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/student-dashboard" element={<StudentDashboard />} />
        <Route path="/teacher-dashboard" element={<TeacherDashboard />} />
        <Route path="/admin-dashboard" element={<AdminDashboard />} />
        <Route path="/active-elections" element={<ActiveElections />} />
        <Route path="/cast-vote" element={<CastVote />} />
        <Route path="/vote-history" element={<VoteHistory />} />
        <Route path="/vote-receipt/:voteId" element={<VoteReceipt />} />
        <Route path="/create-election" element={<CreateElection />} />
        <Route path="/election-drafts" element={<ElectionDraft />} />
        <Route path="/update-election/:electionId" element={<UpdateElection />} />
        <Route path="/election-history" element={<ElectionHistory />} />
        <Route path="/election-results" element={<ElectionResults />} />
        <Route path="/election-detail" element={<ElectionDetail />} />
        <Route path="/manage-users" element={<ManageUsers />} />
        <Route path="/view-account" element={<ViewAccount />} />
        <Route path="/update-account" element={<UpdateAccount />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
