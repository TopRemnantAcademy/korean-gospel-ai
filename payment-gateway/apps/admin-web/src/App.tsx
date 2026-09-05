import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { AdminRole } from '@gospel-pay/shared';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Payments from './pages/Payments';
import Settings from './pages/Settings';
import AuditLogs from './pages/AuditLogs';
import ExternalLogs from './pages/ExternalLogs';
import Consents from './pages/Consents';
import Reconciliation from './pages/Reconciliation';

// Create a dedicated axios instance instead of mutating global defaults
const apiClient = axios.create({
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Response interceptor: auto-logout on 401
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('admin_token');
      window.location.reload();
    }
    return Promise.reject(error);
  }
);

export { apiClient };

interface AdminUserPayload {
  id: string;
  email: string;
  role: AdminRole;
}

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('admin_token'));
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [adminUser, setAdminUser] = useState<AdminUserPayload | null>(null);

  const handleLogout = useCallback(() => {
    localStorage.removeItem('admin_token');
    delete apiClient.defaults.headers.common['Authorization'];
    setToken(null);
    setAdminUser(null);
  }, []);

  useEffect(() => {
    if (token) {
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      // Parse admin user payload from token for UI display only
      // Server-side verification is the source of truth for authorization
      try {
        const parts = token.split('.');
        if (parts.length !== 3) throw new Error('Invalid token format');
        const payload: AdminUserPayload = JSON.parse(atob(parts[1]));
        setAdminUser(payload);
      } catch {
        handleLogout();
      }
    } else {
      delete apiClient.defaults.headers.common['Authorization'];
      setAdminUser(null);
    }
  }, [token, handleLogout]);

  const handleLogin = (newToken: string) => {
    localStorage.setItem('admin_token', newToken);
    setToken(newToken);
    setActiveTab('dashboard');
  };

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  const tabs = [
    { id: 'dashboard', label: '대시보드', icon: '📊' },
    { id: 'payments', label: '결제 & 거래 관리', icon: '💳' },
    { id: 'reconciliation', label: '3자 대조 정산 관리', icon: '⚖️' },
    { id: 'consents', label: '개인정보 동의 로그', icon: '📝' },
    { id: 'external-logs', label: '외부 API 호출 로그', icon: '🌐' },
    { id: 'audit-logs', label: '관리자 감사 로그', icon: '🛡️' },
    { id: 'settings', label: '결제수단 & 시스템 설정', icon: '⚙️' },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col md:flex-row">
      {/* Sidebar */}
      <aside className="w-full md:w-64 bg-slate-900 border-r border-slate-800 flex flex-col justify-between">
        <div>
          {/* Logo */}
          <div className="p-6 border-b border-slate-800 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center font-bold text-sm shadow-md">
              GOSPEL PAY
            </div>
            <span className="font-semibold text-sm tracking-wider bg-gradient-to-r from-violet-400 to-indigo-200 bg-clip-text text-transparent">
              GOSPEL PAY BACKOFFICE
            </span>
          </div>

          {/* Admin Info */}
          {adminUser && (
            <div className="p-4 mx-4 my-3 rounded-xl bg-slate-950/40 border border-slate-800/80 text-xs">
              <div className="text-slate-500">로그인 계정</div>
              <div className="font-medium text-slate-300 truncate mt-0.5">{adminUser.email}</div>
              <div className="mt-1 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                <span className="text-[10px] text-violet-400 font-semibold uppercase">{adminUser.role}</span>
              </div>
            </div>
          )}

          {/* Nav Links */}
          <nav className="p-4 space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                  activeTab === tab.id
                    ? 'bg-violet-600/15 border border-violet-500/30 text-violet-300'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-transparent'
                }`}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>
        </div>

        {/* Logout */}
        <div className="p-4 border-t border-slate-800">
          <button
            onClick={handleLogout}
            className="w-full py-2.5 bg-red-950/20 hover:bg-red-950/40 border border-red-900/30 rounded-xl text-xs font-semibold text-red-400 transition"
          >
            로그아웃
          </button>
        </div>
      </aside>

      {/* Main Panel Content */}
      <main className="flex-grow p-8 overflow-y-auto max-h-screen">
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'payments' && adminUser && <Payments adminUser={adminUser} />}
        {activeTab === 'reconciliation' && <Reconciliation />}
        {activeTab === 'consents' && <Consents />}
        {activeTab === 'external-logs' && <ExternalLogs />}
        {activeTab === 'audit-logs' && <AuditLogs />}
        {activeTab === 'settings' && <Settings />}
      </main>
    </div>
  );
}
