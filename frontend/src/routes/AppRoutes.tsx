import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from './ProtectedRoute';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { DashboardPage } from '@/features/dashboard/pages/DashboardPage';
import { AgentsPage } from '@/features/agents/pages/AgentsPage';
import { ApprovalsPage } from '@/features/approvals/pages/ApprovalsPage';
import { AccountsPage } from '@/features/sales/pages/AccountsPage';
import { ContactsPage } from '@/features/sales/pages/ContactsPage';
import { ConversationsPage } from '@/features/sales/pages/ConversationsPage';
import { DealsPage } from '@/features/sales/pages/DealsPage';
import { WorkflowsPage } from '@/features/workflows/pages/WorkflowsPage';
import { IntegrationsPage } from '@/features/integrations/pages/IntegrationsPage';
import { SettingsPage } from '@/features/settings/pages/SettingsPage';
import { UserListPage } from '@/features/users/pages/UserListPage';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected Routes inside AppShell */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/contacts" element={<ContactsPage />} />
          <Route path="/conversations" element={<ConversationsPage />} />
          <Route path="/deals" element={<DealsPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/partners" element={<AgentsPage />} />
          <Route path="/security" element={<ApprovalsPage />} />
          <Route path="/proof" element={<ApprovalsPage />} />
          <Route path="/visibility" element={<AgentsPage />} />
          <Route path="/revival" element={<AgentsPage />} />
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />

          {/* Admin Protected Route */}
          <Route
            element={<ProtectedRoute allowedRoles={['ADMINISTRATOR', 'SALES_MANAGER']} />}
          >
            <Route path="/users" element={<UserListPage />} />
          </Route>
        </Route>
      </Route>

      {/* Catch-all fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};
