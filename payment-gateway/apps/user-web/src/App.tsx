import React, { useState } from 'react';
import Identify from './pages/Identify';
import Checkout from './pages/Checkout';
import Result from './pages/Result';

export interface UserSession {
  userId: string;
  uid: string;
  emailMasked?: string;
  phoneMasked?: string;
}

export default function App() {
  const [view, setView] = useState<'identify' | 'checkout' | 'result'>('identify');
  const [session, setSession] = useState<UserSession | null>(null);
  const [activePaymentUuid, setActivePaymentUuid] = useState<string>('');

  const handleIdentified = (user: UserSession) => {
    setSession(user);
    setView('checkout');
  };

  const handlePaymentCompleted = (uuid: string) => {
    setActivePaymentUuid(uuid);
    setView('result');
  };

  const handleReset = () => {
    setSession(null);
    setActivePaymentUuid('');
    setView('identify');
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between">
      {/* Header */}
      <header className="border-b border-slate-900 bg-slate-900/40 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center font-bold text-lg shadow-lg shadow-violet-500/20">
              N
            </div>
            <span className="font-semibold text-lg tracking-wider bg-gradient-to-r from-violet-400 to-indigo-200 bg-clip-text text-transparent">
              GOSPEL PAY
            </span>
          </div>

          {session && (
            <div className="flex items-center gap-4 text-sm text-slate-400 bg-slate-900/60 border border-slate-800 rounded-full px-4 py-1.5">
              <span>UID: <strong className="text-violet-400 font-mono">{session.uid.slice(0, 8)}...</strong></span>
              <button 
                onClick={handleReset} 
                className="text-red-400 hover:text-red-300 font-medium transition"
              >
                로그아웃
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-grow max-w-6xl w-full mx-auto px-4 py-12 flex items-center justify-center">
        {view === 'identify' && (
          <Identify onIdentified={handleIdentified} />
        )}
        {view === 'checkout' && session && (
          <Checkout session={session} onPaymentCompleted={handlePaymentCompleted} />
        )}
        {view === 'result' && activePaymentUuid && (
          <Result paymentUuid={activePaymentUuid} onRestart={handleReset} />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-900/20 py-6 text-center text-xs text-slate-600">
        <div className="max-w-6xl mx-auto px-4">
          <p>© 2026 GOSPEL PAY. All rights reserved. 본 시스템은 관련 개인정보보호 및 안전 결제 규정을 준수합니다.</p>
        </div>
      </footer>
    </div>
  );
}
