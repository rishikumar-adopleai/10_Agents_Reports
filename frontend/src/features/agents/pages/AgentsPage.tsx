import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Modal } from '@/components/ui/Modal';
import { LoadingState, ErrorState } from '@/components/ui/FeedbackStates';
import { apiClient } from '@/lib/apiClient';
import { StandardResponse } from '@/types/api';
import { formatDate } from '@/lib/utils';
import {
  Bot,
  Play,
  RotateCw,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  Shield,
  FileText,
  Search,
  Users,
  Compass,
  ArrowRight,
  Info,
} from 'lucide-react';

interface AgentInfo {
  agent_id: string;
  name: string;
  description: string;
  category: string;
  defaultParams: Record<string, any>;
}

const AGENT_CATALOG: AgentInfo[] = [
  {
    agent_id: 'buying_signal_radar',
    name: 'Buying-Signal Radar',
    description: 'Detects intent spikes, high-intent job postings, and leadership changes to prioritize pipeline accounts.',
    category: 'Discovery & Inbound',
    defaultParams: { account_name: 'Acme Health Systems', domain: 'acmehealth.com', min_confidence: 0.8 },
  },
  {
    agent_id: 'research_personal_outreach',
    name: 'Research & Personal Outreach',
    description: 'Researches verified account news and drafts tailored outreach messages strictly capped at 3 attempts.',
    category: 'Engagement',
    defaultParams: { contact_email: 'sarah.c@acmehealth.com', target_pain_point: 'SOC-2 compliance automation' },
  },
  {
    agent_id: 'demo_before_hello',
    name: 'Demo Before Hello',
    description: 'Generates secure, ephemeral synthetic interactive demos customized for target prospect accounts.',
    category: 'Engagement',
    defaultParams: { prospect_industry: 'Healthcare Enterprise', demo_features: ['SSO', 'RBAC', 'Audit Log'] },
  },
  {
    agent_id: 'lead_responder',
    name: '24/7 Lead Responder',
    description: 'Processes inbound SMS/messages with private contact memory, opt-out detection, and meeting booking.',
    category: 'Inbound Response',
    defaultParams: { inbound_message: 'Hi, what are your pricing tiers for enterprise compliance?', from_phone: '+15551234567' },
  },
  {
    agent_id: 'deal_desk',
    name: 'Deal Desk',
    description: 'Generates discovery-gated commercial proposals and ROI models. Never invents unauthorized terms.',
    category: 'Revenue & Closing',
    defaultParams: { discovery_completed: true, requested_seats: 50, contract_term_months: 12 },
  },
  {
    agent_id: 'trust_security_desk',
    name: 'Trust & Security Desk',
    description: 'Completes security questionnaires backed by approved policies; flags missing evidence for human review.',
    category: 'Governance & Security',
    defaultParams: { questionnaire_vendor: 'Whistic', questions: ['Do you encrypt data at rest?', 'Do you support SAML 2.0?'] },
  },
  {
    agent_id: 'proof_engine',
    name: 'Proof Engine',
    description: 'Produces verified delivery case studies and metrics requiring client permissions and delivery owner signs.',
    category: 'Customer Proof',
    defaultParams: { client_approved: true, achieved_roi_percentage: 240, deployment_days: 14 },
  },
  {
    agent_id: 'ai_search_visibility',
    name: 'AI Search Visibility',
    description: 'Monitors citation share of voice across ChatGPT, Perplexity, and Claude to build technical content briefs.',
    category: 'Brand & Inbound',
    defaultParams: { target_query: 'best enterprise sales agent platform', competitor_check: true },
  },
  {
    agent_id: 'partner_finder',
    name: 'Partner Finder',
    description: 'Discovers non-competing co-sell partners and creates custom enablement kits with zero channel conflict.',
    category: 'Ecosystem',
    defaultParams: { partner_category: 'Cloud Security Systems Integrators', region: 'North America' },
  },
  {
    agent_id: 'revival_agent',
    name: 'Revival Agent',
    description: 'Reconnects dormant lost deals when fresh verified triggers occur. Strictly checks suppression registry.',
    category: 'Pipeline Revival',
    defaultParams: { dormant_days: 90, revival_trigger: 'New Executive Security Officer Appointed' },
  },
];

export const AgentsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [paramInput, setParamInput] = useState<string>('{}');
  const [executionResult, setExecutionResult] = useState<any | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // Fetch recent tasks
  const { data: recentTasks = [], isLoading: tasksLoading } = useQuery({
    queryKey: ['agent-tasks', 'recent'],
    queryFn: async () => {
      const res = await apiClient.get<StandardResponse<any[]>>('/agent-tasks');
      return res.data.data;
    },
    refetchInterval: 5000,
  });

  const handleOpenRunner = (agent: AgentInfo) => {
    setSelectedAgent(agent);
    setParamInput(JSON.stringify(agent.defaultParams, null, 2));
    setExecutionResult(null);
  };

  const handleExecute = async () => {
    if (!selectedAgent) return;
    setIsExecuting(true);
    setExecutionResult(null);

    try {
      let parsedParams = {};
      try {
        parsedParams = JSON.parse(paramInput);
      } catch {
        parsedParams = { raw: paramInput };
      }

      const payload = {
        agent_id: selectedAgent.agent_id,
        organization_id: 'org-default',
        correlation_id: `corr-${Date.now()}`,
        parameters: parsedParams,
      };

      const res = await apiClient.post<StandardResponse<any>>('/agent-tasks/execute', payload);
      setExecutionResult(res.data.data);
      queryClient.invalidateQueries({ queryKey: ['agent-tasks'] });
    } catch (err: any) {
      setExecutionResult({
        error: err.response?.data?.message || err.message || 'Execution error occurred',
        status: 'terminal_failure',
      });
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Specialized Agent Fleet Hub"
        description="Ten production-grade agents operating under strict RBAC, human approval gates, and deterministic attempt limits."
      />

      {/* Grid of 10 Agents */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {AGENT_CATALOG.map((agent, idx) => (
          <div
            key={agent.agent_id}
            className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-xs hover:border-brand-500 hover:shadow-md transition-all flex flex-col justify-between space-y-4"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-semibold">
                  0{idx + 1} // {agent.category}
                </span>
                <span className="flex items-center space-x-1.5 text-xs text-emerald-600 font-medium">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>Ready</span>
                </span>
              </div>

              <h4 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-1.5">
                {agent.name}
              </h4>
              <p className="text-xs text-slate-500 leading-relaxed">{agent.description}</p>
            </div>

            <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <span className="text-[11px] font-mono text-slate-400 select-all">
                {agent.agent_id}
              </span>
              <Button size="sm" onClick={() => handleOpenRunner(agent)}>
                <Play className="w-3.5 h-3.5 mr-1.5" />
                Configure & Run
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Execution Audit Stream */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Clock className="w-4 h-4 text-brand-600" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Live Agent Execution Stream
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">Auto-refreshes every 5s</span>
        </div>

        {tasksLoading ? (
          <p className="text-xs text-slate-400">Loading execution records...</p>
        ) : recentTasks.length === 0 ? (
          <p className="text-xs text-slate-500 py-3">
            No agent execution records recorded yet. Launch an agent above to see real-time task outputs.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400 font-semibold">
                  <th className="py-2.5 px-3">Agent</th>
                  <th className="py-2.5 px-3">Execution ID</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Uncertainty</th>
                  <th className="py-2.5 px-3">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-mono">
                {recentTasks.map((task: any) => (
                  <tr key={task.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="py-2 px-3 font-semibold text-slate-800 dark:text-slate-200">
                      {task.agent_id}
                    </td>
                    <td className="py-2 px-3 text-slate-500">{task.execution_id.slice(0, 8)}...</td>
                    <td className="py-2 px-3">
                      <Badge
                        variant={
                          task.status === 'completed'
                            ? 'success'
                            : task.status === 'waiting_for_review'
                            ? 'warning'
                            : 'default'
                        }
                      >
                        {task.status}
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-slate-500">{task.uncertainty ?? '0.00'}</td>
                    <td className="py-2 px-3 text-slate-400">{task.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Runner Modal */}
      <Modal
        isOpen={Boolean(selectedAgent)}
        onClose={() => setSelectedAgent(null)}
        title={`Execute Agent: ${selectedAgent?.name || ''}`}
        maxWidth="2xl"
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-500">{selectedAgent?.description}</p>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
              Input Parameters (JSON Schema)
            </label>
            <textarea
              rows={5}
              value={paramInput}
              onChange={(e) => setParamInput(e.target.value)}
              className="w-full p-3 font-mono text-xs bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-brand-500 focus:outline-hidden text-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex justify-end space-x-3 pt-2">
            <Button
              variant="outline"
              onClick={() => setSelectedAgent(null)}
              disabled={isExecuting}
            >
              Close
            </Button>
            <Button onClick={handleExecute} isLoading={isExecuting}>
              <Play className="w-4 h-4 mr-1.5" />
              Dispatch Execution
            </Button>
          </div>

          {/* Structured Execution Result */}
          {executionResult && (
            <div className="mt-4 p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2">
                <span className="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center space-x-1.5">
                  <Sparkles className="w-4 h-4 text-brand-600" />
                  <span>Execution Output</span>
                </span>
                <Badge
                  variant={
                    executionResult.status === 'completed'
                      ? 'success'
                      : executionResult.status === 'waiting_for_review'
                      ? 'warning'
                      : 'danger'
                  }
                >
                  {executionResult.status || 'unknown'}
                </Badge>
              </div>

              {executionResult.proposed_next_actions &&
                executionResult.proposed_next_actions.length > 0 && (
                  <div>
                    <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                      Proposed Next Actions:
                    </span>
                    <ul className="text-xs text-slate-700 dark:text-slate-300 list-disc list-inside space-y-0.5">
                      {executionResult.proposed_next_actions.map((act: string, i: number) => (
                        <li key={i}>{act}</li>
                      ))}
                    </ul>
                  </div>
                )}

              <div>
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                  Structured Payload:
                </span>
                <pre className="p-3 bg-white dark:bg-slate-900 rounded-lg text-[11px] font-mono text-slate-700 dark:text-slate-300 overflow-x-auto max-h-48 border border-slate-200 dark:border-slate-800">
                  {JSON.stringify(
                    executionResult.structured_result || executionResult,
                    null,
                    2
                  )}
                </pre>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};
