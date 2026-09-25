"use client";

import { useEffect, useState } from 'react';
import { ShieldCheck, Zap } from 'lucide-react';
import { useMarketData } from '@/hooks/useMarketData';
import { usePendingApprovals, type PendingOrder } from '@/hooks/usePendingApprovals';
import { API_URL, apiFetch } from '@/lib/api';

type Position = { symbol: string; qty: number; avg_price: number; mark: number; unrealized_usd: number };

type Portfolio = {
  balances?: Record<string, number>;
  positions?: Position[];
  metrics?: {
    equity?: number;
    cash?: number;
    unrealized_pnl?: number;
    margin_used?: number;
    free_margin?: number;
    leverage?: number;
    daily_pnl_pct?: number;
    drawdown_pct?: number;
    unpriced_positions?: string[];
  };
  error?: string;
};

// A value that rounds to zero cents shows as $0.00, never -$0.00.
const usd = (n: number) => (Math.abs(n) < 0.005 ? 0 : n).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
const pct = (n: number) => `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`;

export default function Dashboard() {
  const { tickers, connected } = useMarketData();
  const { approvals, handleApproval } = usePendingApprovals();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);

  useEffect(() => {
    const fetchPortfolio = async () => {
      try {
        const res = await apiFetch('/api/portfolio');
        if (res.status === 401) {
          setPortfolioError('The API requires its operator token (API_OPERATOR_TOKEN): reload the page to enter it.');
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setPortfolio(await res.json());
        setPortfolioError(null);
      } catch {
        setPortfolioError(`The API is not reachable at ${API_URL}. Start it with: python app/api_server.py`);
      }
    };
    fetchPortfolio();
    const timer = setInterval(fetchPortfolio, 15000);
    return () => clearInterval(timer);
  }, []);

  // The API approves or rejects a proposal only with its confirm_token, which the agent received
  // when it placed the order; an approval re-runs the Risk Guardian before anything executes.
  const review = async (requestId: string, approve: boolean) => {
    const verb = approve ? 'approve' : 'reject';
    const token = window.prompt(`Paste the confirm_token your agent received with this proposal to ${verb} it:`);
    if (!token) return;
    const ok = await handleApproval(requestId, token.trim(), approve);
    window.alert(
      approve
        ? ok
          ? 'Approved: the trade was re-checked and executed.'
          : 'Not approved: the token was wrong, the proposal expired, or the Risk Guardian refused it on re-check.'
        : ok
          ? 'Rejected: the proposal was cancelled.'
          : 'Not rejected: the token was wrong or the proposal is no longer pending.'
    );
  };

  const describe = (o?: PendingOrder) =>
    o && o.symbol
      ? `${(o.side ?? '').toUpperCase()} ${Number(o.amount ?? 0).toLocaleString()} ${o.symbol} ${o.order_type ?? 'market'}` +
        `${o.price ? ` @ ${o.price}` : ''}${o.paper_mode === false ? ` - LIVE via ${o.exchange ?? '?'}` : ' - paper account'}`
      : 'Order details unavailable';

  const metrics = portfolio?.metrics;
  const positions = portfolio?.positions ?? [];

  return (
    <div className="dashboard-grid">
      {/* Paper account */}
      <section className="col-span-2 card">
        <div className="card-header">
          <div>
            <h3>Paper Account</h3>
            <p className="muted">Cash, open positions and margin, from the API</p>
          </div>
          {metrics?.equity !== undefined && (
            <div className="value-pnl">
              <h2>{usd(metrics.equity)}</h2>
              {metrics.daily_pnl_pct !== undefined && (
                <span className={metrics.daily_pnl_pct >= 0 ? 'success' : 'danger'}>{pct(metrics.daily_pnl_pct)} today</span>
              )}
            </div>
          )}
        </div>
        {portfolioError ? (
          <p className="muted">{portfolioError}</p>
        ) : portfolio?.error ? (
          <p className="muted">{portfolio.error}</p>
        ) : !portfolio ? (
          <p className="muted">Loading…</p>
        ) : !metrics?.equity && positions.length === 0 ? (
          <p className="muted">The paper account is empty. Fund it with deposit_paper_funds(&quot;USD&quot;, amount).</p>
        ) : (
          <div className="strategy-list">
            <div className="strategy-item">
              <span>Cash</span>
              <span>{usd(metrics?.cash ?? 0)}</span>
            </div>
            {positions.map((p) => (
              <div key={p.symbol} className="strategy-item">
                <span>
                  {p.symbol} {p.qty > 0 ? 'long' : 'short'} {Math.abs(p.qty).toLocaleString()} @ {p.avg_price.toFixed(5)}
                </span>
                <span className={p.unrealized_usd >= 0 ? 'success' : 'danger'}>{usd(p.unrealized_usd)}</span>
              </div>
            ))}
            <div className="strategy-item">
              <span className="muted">Margin used / free ({metrics?.leverage ?? '?'}x)</span>
              <span>
                {usd(metrics?.margin_used ?? 0)} / {usd(metrics?.free_margin ?? 0)}
              </span>
            </div>
            {metrics?.drawdown_pct !== undefined && (
              <div className="strategy-item">
                <span className="muted">Drawdown from peak</span>
                <span>{(metrics.drawdown_pct * 100).toFixed(2)}%</span>
              </div>
            )}
            {metrics?.unpriced_positions && metrics.unpriced_positions.length > 0 && (
              <p className="danger">
                No rate for {metrics.unpriced_positions.join(', ')}: shown at the entry price, so equity and P&amp;L leave out
                its move; orders that add exposure are refused until it can be priced.
              </p>
            )}
          </div>
        )}
      </section>

      {/* Real-time Ticker */}
      <section className="card">
        <div className="card-header">
          <h3>Live Markets</h3>
          <span className={`connection-dot ${connected ? 'online' : 'offline'}`}></span>
        </div>
        <div className="ticker-list">
          {Object.values(tickers).length === 0 ? (
            <p className="muted">No market-data stream is running.</p>
          ) : (
            Object.values(tickers).map((t) => (
              <div key={t.symbol} className="ticker-item">
                <span className="symbol">{t.symbol}</span>
                <span className="price">{t.last.toLocaleString()}</span>
                <span className="source muted">{t.source}</span>
              </div>
            ))
          )}
        </div>
      </section>

      {/* Guard Rail / Pending Approvals */}
      <section className="card">
        <div className="card-header">
          <div className="icon-title">
            <ShieldCheck className="primary" size={20} />
            <h3>Guard Rail</h3>
          </div>
          {approvals.length > 0 && <span className="warning-badge">{approvals.length}</span>}
        </div>
        <div className="approval-list">
          {approvals.length === 0 ? (
            <div className="empty-approval">
              <Zap className="muted" size={32} />
              <p className="muted">No pending approvals</p>
            </div>
          ) : (
            approvals.map((a) => (
              <div key={a.request_id} className="approval-item">
                <div className="approval-info">
                  <span className="kind">{describe(a.order)}</span>
                  {a.order?.rationale && <span className="muted">{a.order.rationale}</span>}
                  <span className="muted">ID: {a.request_id.slice(0, 8)}...</span>
                </div>
                <div className="approval-actions">
                  <button className="btn btn-primary compact" onClick={() => review(a.request_id, true)}>
                    Approve
                  </button>
                  <button className="btn compact" onClick={() => review(a.request_id, false)}>
                    Reject
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}