import React, { useState } from 'react';
import { LogOut, Moon, Sun, Bell } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { apiClient } from '@/lib/apiClient';

export const Navbar: React.FC = () => {
  const { user, logout } = useAuthStore();
  const [isDark, setIsDark] = useState(false);

  const toggleDarkMode = () => {
    setIsDark(!isDark);
    document.documentElement.classList.toggle('dark');
  };

  const handleLogout = async () => {
    try {
      await apiClient.post('/auth/logout');
    } catch {
      // Ignored
    } finally {
      logout();
      window.location.href = '/login';
    }
  };

  const userInitials = user ? `${user.first_name[0]}${user.last_name[0]}`.toUpperCase() : 'U';
  const primaryRole = user?.roles[0]?.name.replace('_', ' ') || 'User';

  return (
    <header className="h-16 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between px-8 sticky top-0 z-40">
      <div className="flex items-center space-x-4">
        <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2.5 py-1 rounded-md font-mono">
          TEN-AGENT MODULAR MONOLITH
        </span>
      </div>

      <div className="flex items-center space-x-5">
        <button
          onClick={toggleDarkMode}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="Toggle Dark Mode"
        >
          {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        <div className="flex items-center space-x-3 pl-3 border-l border-slate-200 dark:border-slate-800">
          <div className="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900 text-brand-700 dark:text-brand-300 font-bold text-xs flex items-center justify-center border border-brand-200 dark:border-brand-800">
            {userInitials}
          </div>
          <div className="text-left hidden md:block">
            <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">
              {user?.first_name} {user?.last_name}
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase font-medium">{primaryRole}</p>
          </div>

          <button
            onClick={handleLogout}
            className="p-1.5 ml-2 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Log out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
