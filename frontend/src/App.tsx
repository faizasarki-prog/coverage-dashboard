import { Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import DashboardPlaceholder from './pages/DashboardPlaceholder';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<DashboardPlaceholder />} />
      <Route path="*" element={<DashboardPlaceholder />} />
    </Routes>
  );
}
