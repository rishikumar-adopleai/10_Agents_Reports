import React from 'react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Building2,
  CheckSquare,
  Bot,
  TrendingUp,
  ShieldCheck,
  ArrowRight,
  Activity,
  Sparkles,
  Zap,
} from 'lucide-react';

const STATS = [
  { label: 'Target Accounts', value: '142', change: '+12% this mo', icon: Building2, color: 'text-blue-600 bg-blue-50 dark:bg-blue-950/40' },
  { label: 'Monitored Contacts', value: '618', change: 'Max 3 outreach cap', icon: Users, color: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40' },
  { label: 'Pending Approvals', value: '4', change: 'Human review required', icon: CheckSquare, color: 'text-amber-600 bg-amber-50 dark:bg-amber-950/40' },
  { label: 'Agent Executions', value: '1,842', change: '100% deterministic gate', icon: Bot, color: 'text-purple-600 bg-purple-50 dark:bg-purple-950/40' },
];

const TEN_AGENTS = [
  { id: 'buying_signal_radar', name: 'Buying-Signal Radar', status: 'active', desc: 'Monitors intent spikes, hiring signals, and tech changes' },
  { id: 'research_personal_outreach', name: 'Research & Outreach', status: 'active', desc: 'Generates evidence-backed personalized emails (max 3)' },
  { id: 'demo_before_hello', name: 'Demo Before Hello', status: 'active', desc: 'Provisions ephemeral interactive product environments' },
  { id: 'lead_responder', name: '24/7 Lead Responder', status: 'active', desc: 'Handles inbound SMS with private contact memory' },
  { id: 'deal_desk', name: 'Deal Desk', status: 'active', desc: 'Discovery-gated proposals & automated ROI calculation' },
  { id: 'trust_security_desk', name: 'Trust & Security Desk', status: 'active', desc: 'Fills security questionnaires using approved evidence' },
  { id: 'proof_engine', name: 'Proof Engine', status: 'active', desc: 'Verified delivery case studies & approved testimonials' },
  { id: 'ai_search_visibility', name: 'AI Search Visibility', status: 'active', desc: 'Monitors LLM citations & produces targeted content briefs' },
  { id: 'partner_finder', name: 'Partner Finder', status: 'active', desc: 'Identifies non-competing co-sellers & enablement kits' },
  { id: 'revival_agent', name: 'Revival Agent', status: 'active', desc: 'Reconnects dormant deals with fresh verified triggers' },
];

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="space-y-8">
      <PageHeader
        title="Executive Control Center"
        description="Unified operations for ten specialized enterprise AI agents across the sales and revenue lifecycle."
        action={
          <div className="flex space-x-3">
            <Button variant="outline" onClick={() => navigate('/approvals')}>
              <CheckSquare className="w-4 h-4 mr-2 text-amber-500" />
              Approvals Gate (4)
            </Button>
            <Button onClick={() => navigate('/agents')}>
              <Zap className="w-4 h-4 mr-2" />
              Run Agent
            </Button>
          </div>
        }
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {STATS.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.label}
              className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs flex items-center justify-between"
            >
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  {stat.label}
                </p>
                <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 mt-1">
                  {stat.value}
                </p>
                <p className="text-[11px] text-slate-400 mt-1 flex items-center space-x-1">
                  <Activity className="w-3 h-3 text-brand-600" />
                  <span>{stat.change}</span>
                </p>
              </div>
              <div className={`p-3 rounded-xl ${stat.color}`}>
                <Icon className="w-6 h-6" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Ten Agents Hub Overview */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-xs space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <Bot className="w-5 h-5 text-brand-600" />
              <span>Specialized Autonomous Agent Fleet</span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Ten production-grade agents operating under strict RBAC, outbox idempotency, and human review boundaries.
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => navigate('/agents')}>
            View Agent Hub
            <ArrowRight className="w-4 h-4 ml-1.5" />
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {TEN_AGENTS.map((agent, idx) => (
            <div
              key={agent.id}
              onClick={() => navigate(`/agents?agent=${agent.id}`)}
              className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-brand-500 dark:hover:border-brand-500 bg-slate-50/50 dark:bg-slate-850/40 hover:bg-white dark:hover:bg-slate-800 cursor-pointer transition-all flex flex-col justify-between space-y-3 group"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono text-slate-400">0{idx + 1}</span>
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                </div>
                <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 group-hover:text-brand-600 transition-colors">
                  {agent.name}
                </h4>
                <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">{agent.desc}</p>
              </div>
              <div className="pt-2 border-t border-slate-200/60 dark:border-slate-800 flex items-center justify-between text-[10px] font-semibold text-brand-600">
                <span>Configure & Run</span>
                <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Governance & Safeguards Highlights */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
          <div className="flex items-center space-x-2 text-brand-600 mb-2">
            <ShieldCheck className="w-5 h-5" />
            <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Deterministic Outreach Cap
            </h4>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Strict maximum of 3 logical outreach attempts per contact across all agents. Technical retries do not increment logical attempts.
          </p>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
          <div className="flex items-center space-x-2 text-amber-600 mb-2">
            <CheckSquare className="w-5 h-5" />
            <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Human-in-the-Loop Gateway
            </h4>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            LLMs never authorize external emails, proposals, or SMS replies directly. Authorized staff review and approve every external side effect.
          </p>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
          <div className="flex items-center space-x-2 text-emerald-600 mb-2">
            <Sparkles className="w-5 h-5" />
            <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Discovery-Gated Proposals
            </h4>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Deal Desk refuses proposal generation until discovery is verified. Pricing and contractual terms require commercial approval.
          </p>
        </div>
      </div>
    </div>
  );
};
