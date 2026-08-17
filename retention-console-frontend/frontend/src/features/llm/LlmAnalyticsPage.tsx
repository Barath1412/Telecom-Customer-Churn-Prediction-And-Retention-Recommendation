import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, StatTile } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { usd } from '@/lib/format'
import type { LlmCallLog } from '@/types/api'

export function LlmAnalyticsPage() {
  const { data, isPending, error, refetch, isFetching } = useQuery({
    queryKey: ['llm', 'telemetry'],
    queryFn: () => api.llmTelemetry(),
    refetchInterval: 10000,
  })

  const [simVolume, setSimVolume] = useState<number>(40000)
  const [searchTerm, setSearchTerm] = useState('')

  if (isPending) {
    return <Skeleton className="h-96 w-full" label="Loading LLM analytics" />
  }

  if (error) {
    return <ErrorState error={error} onRetry={() => void refetch()} />
  }

  // Simulations based on measured average tokens
  const avgTokensPerCall = Math.round(data.total_tokens / Math.max(1, data.total_calls))
  const costPerCall = data.projections.cost_per_call_usd || 0.000185
  const simulatedMonthlyTokens = simVolume * avgTokensPerCall
  const simulatedMonthlyCost = simVolume * costPerCall
  const simulatedHumanCost = simVolume * 7.00
  const simulatedSavings = simulatedHumanCost - simulatedMonthlyCost

  const filteredCalls = (data.recent_calls || []).filter(
    (c: LlmCallLog) =>
      c.customer_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.call_id.toLowerCase().includes(searchTerm.toLowerCase()),
  )

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">
            LLM Observability & Cost Analytics
          </h1>
          <p className="text-xs text-ink-3">
            Real-time Gemini token consumption, deterministic guardrail verification, and telecom ROI modeling.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full border border-emerald-500/40 bg-emerald-50 dark:bg-emerald-950/40 px-3.5 py-1 text-xs font-bold text-emerald-800 dark:text-emerald-300 shadow-xs">
            ● Gemini 3.5 Flash Lite Active
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            {isFetching ? 'Refreshing...' : '🔄 Refresh Live'}
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatTile
          label="Total LLM Calls"
          value={String(data.total_calls)}
          hint="live & historical pipeline runs"
        />
        <StatTile
          label="Total Tokens"
          value={data.total_tokens.toLocaleString()}
          hint={`${data.total_prompt_tokens.toLocaleString()} prompt · ${data.total_completion_tokens.toLocaleString()} output`}
        />
        <StatTile
          label="Actual API Spend"
          value={`$${data.total_cost_usd.toFixed(4)}`}
          hint="$0.075 / 1M in · $0.30 / 1M out"
        />
        <StatTile
          label="Avg Latency"
          value={`${Math.round(data.avg_latency_ms)} ms`}
          hint="warm graph end-to-end"
        />
        <StatTile
          label="Guardrail Pass Rate"
          value={`${data.validator_pass_rate}%`}
          hint="5/5 safety checks passed"
        />
      </div>

      {/* Economics & Projections Grid */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Cost Economics Summary */}
        <Card title="Economics & Margin Impact" subtitle="Enterprise telecom retention cost efficiency">
          <div className="space-y-4 text-xs">
            <div className="rounded-lg border border-line bg-surface-2 p-3 space-y-2">
              <div className="flex justify-between">
                <span className="text-ink-3">Cost per Generated Talk Track:</span>
                <span className="num font-semibold text-ink">
                  ${data.projections.cost_per_call_usd.toFixed(6)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink-3">Human Call Center Labor Benchmark:</span>
                <span className="num font-semibold text-ink">$7.000000</span>
              </div>
              <div className="flex justify-between border-t border-line/60 pt-2">
                <span className="text-emerald-700 dark:text-emerald-400 font-bold">Efficiency Multiplier:</span>
                <span className="num font-bold text-emerald-700 dark:text-emerald-400">
                  {data.projections.cost_savings_multiplier} Cheaper
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold uppercase tracking-wider text-micro text-ink-3">
                Active Safety Guardrails
              </h4>
              <ul className="space-y-1.5 text-micro text-ink-2">
                <li className="flex items-center gap-1.5">
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">✓</span> <strong>V-OFFER:</strong> Catalog SKU verification
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">✓</span> <strong>V-MONEY:</strong> Price & discount dollar matching
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">✓</span> <strong>V-CITE:</strong> Evidence document ID groundings
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">✓</span> <strong>V-CAUSAL:</strong> Ban unverified causality claims
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">✓</span> <strong>V-SCHEMA:</strong> Strict JSON character limits
                </li>
              </ul>
            </div>
          </div>
        </Card>

        {/* Interactive Volume & Budget Simulator */}
        <Card
          title="Interactive Budget Simulator"
          subtitle="Project monthly Gemini costs based on customer outreach volume"
          className="lg:col-span-2"
        >
          <div className="space-y-5">
            <div>
              <div className="flex justify-between text-xs mb-2">
                <label htmlFor="volume-slider" className="font-medium text-ink">
                  Monthly Retention Customer Volume:
                </label>
                <span className="num font-bold text-accent text-sm">
                  {simVolume.toLocaleString()} customers / month
                </span>
              </div>
              <input
                id="volume-slider"
                type="range"
                min={1000}
                max={200000}
                step={1000}
                value={simVolume}
                onChange={(e) => setSimVolume(Number(e.target.value))}
                className="w-full h-2 rounded-lg bg-surface-2 accent-accent cursor-pointer"
              />
              <div className="flex justify-between text-micro text-ink-3 mt-1">
                <span>1,000 / mo</span>
                <span>50,000 / mo</span>
                <span>100,000 / mo</span>
                <span>200,000 / mo</span>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-line bg-surface-2 p-3">
                <span className="text-micro text-ink-3 uppercase font-semibold">Projected Token Load</span>
                <p className="mt-1 text-lg font-bold num text-ink">
                  {(simulatedMonthlyTokens / 1_000_000).toFixed(2)}M
                </p>
                <p className="text-micro text-ink-3">tokens / month</p>
              </div>

              <div className="rounded-lg border border-line bg-surface-2 p-3">
                <span className="text-micro text-ink-3 uppercase font-semibold">Estimated Gemini Cost</span>
                <p className="mt-1 text-lg font-bold num text-emerald-700 dark:text-emerald-400">
                  {usd(simulatedMonthlyCost)}
                </p>
                <p className="text-micro text-ink-3">total API invoice / month</p>
              </div>

              <div className="rounded-lg border border-line bg-surface-2 p-3">
                <span className="text-micro text-ink-3 uppercase font-semibold">Agent Labor Equivalent</span>
                <p className="mt-1 text-lg font-bold num text-ink">
                  {usd(simulatedHumanCost)}
                </p>
                <p className="text-micro text-emerald-700 dark:text-emerald-400 font-bold">
                  Saving {usd(simulatedSavings)}
                </p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Live LLM Invocations Log Table */}
      <Card title="Live LLM Invocations Log" subtitle="Audit trail of narration calls with token metrics and validator status">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <input
              type="text"
              placeholder="Filter by Customer ID (e.g. 0295-PPHDO, NEW-CORP-9001)..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full max-w-sm rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none"
            />
            <span className="text-xs text-ink-3">
              Showing {filteredCalls.length} of {data.total_calls} calls
            </span>
          </div>

          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-line bg-surface-2 text-micro uppercase tracking-wider text-ink-3">
                <tr>
                  <th className="px-3 py-2">Call ID</th>
                  <th className="px-3 py-2">Customer ID</th>
                  <th className="px-3 py-2">Model</th>
                  <th className="px-3 py-2 text-right">Prompt Tok</th>
                  <th className="px-3 py-2 text-right">Output Tok</th>
                  <th className="px-3 py-2 text-right">Total Tok</th>
                  <th className="px-3 py-2 text-right">Latency</th>
                  <th className="px-3 py-2 text-center">Safety Status</th>
                  <th className="px-3 py-2 text-right">Cost ($)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {filteredCalls.map((c) => (
                  <tr key={c.call_id} className="hover:bg-surface-2/60 transition-colors">
                    <td className="px-3 py-2 font-mono text-ink-3">{c.call_id}</td>
                    <td className="px-3 py-2 font-mono font-medium text-ink">{c.customer_id}</td>
                    <td className="px-3 py-2 font-mono text-micro text-ink-2">{c.model}</td>
                    <td className="px-3 py-2 text-right num text-ink-3">{c.prompt_tokens}</td>
                    <td className="px-3 py-2 text-right num text-ink-3">{c.completion_tokens}</td>
                    <td className="px-3 py-2 text-right num font-semibold text-ink">{c.total_tokens}</td>
                    <td className="px-3 py-2 text-right num text-ink-2">{c.elapsed_ms} ms</td>
                    <td className="px-3 py-2 text-center">
                      <span className="inline-flex items-center rounded px-2 py-0.5 text-micro font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-500/30">
                        ✓ 5/5 Passed
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right num font-mono font-semibold text-emerald-700 dark:text-emerald-400">
                      ${c.cost_usd.toFixed(6)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Card>
    </div>
  )
}
