import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Bot,
  CheckSquare,
  Building2,
  Users,
  MessageSquare,
  DollarSign,
  GitBranch,
  ShieldCheck,
  Award,
  Search,
  Handshake,
  RotateCcw,
  Sliders,
  UserCog,
  Plug,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/authStore';

interface NavItem {
  name: string;
  to: string;
  icon: React.ElementType;
  badge?: string;
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  { name: 'Dashboard', to: '/dashboard', icon: LayoutDashboard },
  { name: 'Agents Hub', to: '/agents', icon: Bot, badge: '10' },
  { name: 'Approval Center', to: '/approvals', icon: CheckSquare },
  { name: 'Accounts', to: '/accounts', icon: Building2 },
  { name: 'Contacts', to: '/contacts', icon: Users },
  { name: 'Conversations', to: '/conversations', icon: MessageSquare },
  { name: 'Deals & Pipeline', to: '/deals', icon: DollarSign },
  { name: 'Workflows', to: '/workflows', icon: GitBranch },
  { name: 'Partners', to: '/partners', icon: Handshake },
  { name: 'Security Desk', to: '/security', icon: ShieldCheck },
  { name: 'Proof Engine', to: '/proof', icon: Award },
  { name: 'AI Visibility', to: '/visibility', icon: Search },
  { name: 'Revival', to: '/revival', icon: RotateCcw },
  { name: 'Users & RBAC', to: '/users', icon: UserCog, adminOnly: true },
  { name: 'Integrations', to: '/integrations', icon: Plug },
  { name: 'Settings', to: '/settings', icon: Sliders },
];

export const Sidebar: React.FC = () => {
  const { user } = useAuthStore();
  const isAdmin = user?.roles.some((r) => r.name === 'ADMINISTRATOR' || r.name === 'SALES_MANAGER');

  return (
    <aside className="w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col h-screen sticky top-0 select-none">
      <div className="h-16 flex items-center px-6 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center text-white font-bold text-lg shadow-sm">
            Δ
          </div>
          <div>
            <span className="font-bold text-sm tracking-tight text-slate-900 dark:text-slate-100 block">
              Enterprise Sales
            </span>
            <span className="text-[10px] text-brand-600 font-medium tracking-wide uppercase block">
              Agent Platform
            </span>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {navItems.map((item) => {
          if (item.adminOnly && !isAdmin) return null;
          const Icon = item.icon;

          return (
            <NavLink
              key={item.name}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/60 dark:text-brand-300 font-semibold'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100'
                )
              }
            >
              <div className="flex items-center space-x-3">
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.name}</span>
              </div>
              {item.badge && (
                <span className="text-[10px] bg-brand-100 dark:bg-brand-900 text-brand-700 dark:text-brand-300 px-1.5 py-0.5 rounded-full font-bold">
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="p-4 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-400">
        <p className="font-semibold text-slate-600 dark:text-slate-300">Acme Corporation</p>
        <p className="text-[11px] text-slate-400">Production Foundation v1.0</p>
      </div>
    </aside>
  );
};
