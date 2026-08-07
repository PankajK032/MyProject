export type StockResult = {
  ticker: string;
  score: number;
  max_score: number;
  close: number;
  rsi: number | null;
  pe: number | null;
  roe_pct: number | null;
  debt_to_equity: number | null;
  stop_loss: number;
  target: number;
  reward_risk: number | null;
};

function fmt(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined) return '\u2014';
  return `${value}${suffix}`;
}

export default function StockCard({ stock }: { stock: StockResult }) {
  const scoreRatio = stock.score / stock.max_score;
  const scoreColor =
    scoreRatio >= 0.8 ? 'text-signal-green' : scoreRatio >= 0.65 ? 'text-signal-gold' : 'text-ink-muted';

  return (
    <div className="rounded-lg border border-base-border bg-base-surface p-4 transition-colors hover:border-ink-faint">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-base font-bold tracking-tight text-ink-primary">
          {stock.ticker}
        </span>
        <span className={`font-mono text-xs font-semibold ${scoreColor}`}>
          {stock.score}/{stock.max_score}
        </span>
      </div>

      <div className="mb-3 grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-ink-faint">Stop-loss</div>
          <div className="tabular font-mono text-sm font-semibold text-signal-rust">
            ₹{fmt(stock.stop_loss)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-ink-faint">Buy</div>
          <div className="tabular font-mono text-sm font-semibold text-ink-primary">
            ₹{fmt(stock.close)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-ink-faint">Target</div>
          <div className="tabular font-mono text-sm font-semibold text-signal-green">
            ₹{fmt(stock.target)}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-base-border pt-2 font-mono text-[11px] text-ink-muted">
        <span>RSI {fmt(stock.rsi)}</span>
        <span>P/E {fmt(stock.pe)}</span>
        <span>ROE {fmt(stock.roe_pct, '%')}</span>
        <span>D/E {fmt(stock.debt_to_equity)}</span>
      </div>
    </div>
  );
}
