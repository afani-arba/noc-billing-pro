import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Technician from './pages/Technician';
import Collector from './pages/Collector';

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { token, user } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user?.role)) {
    return <div className="p-8 text-center text-red-500">Akses Ditolak. Role Anda: {user?.role}</div>;
  }
  return children;
};

const RootRedirect = () => {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === 'teknisi') return <Navigate to="/teknisi" replace />;
  if (user.role === 'kolektor') return <Navigate to="/kolektor" replace />;
  return <div className="p-8 text-center">Akun Anda bukan Teknisi atau Kolektor.</div>;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50 pb-safe">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/teknisi" element={
              <ProtectedRoute allowedRoles={['teknisi', 'administrator', 'super_admin']}>
                <Technician />
              </ProtectedRoute>
            } />
            <Route path="/kolektor" element={
              <ProtectedRoute allowedRoles={['kolektor', 'administrator', 'super_admin']}>
                <Collector />
              </ProtectedRoute>
            } />
            <Route path="/" element={<RootRedirect />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
