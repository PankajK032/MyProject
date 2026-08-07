'use client';

import { useEffect, useState } from 'react';
import StockCard, { StockResult } from '@/components/StockCard';
import { MOCK_RESULTS } from '@/lib/mock-data';

// Raw content URL for your own repo's daily output - updates automatically
// every time the screener workflow commits a new latest_screen.json.
const RESULTS_URL =
  'https://raw.githubusercontent.com/PankajK032/MyProject/main/latest_screen.json';

export default function DashboardPage() {
  const [results, setResults] = useState<StockResult[] | null>(null);
  const [usingMock, setUsingMock] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${RESULTS_URL}?t=${Date.now()}`) // cache-bust so it doesn't show yesterday's data all day
      .then((res) => {
        if (!res.ok) throw new Error(`GitHub returned ${res.status}`);
        return res.json();
      })
      .then((data: StockResult[]) => {
        setResults(data);
        setUsingMock(false);
      })
      .catch(() => {
        setResults(MOCK_RESULTS);
        setUsingMock(true);
      })
      .finally(() => setLoading(false));
  }, []);

  const passed = results?.length ?? 0;

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-8">
        <h1 className="font-mono text-xl font-bold tracking-tight text-ink-primary">
          Market Dashboard
        </h1>
        <p className="mt-1 font-mono text-xs text-ink-muted">
          {loading ? 'Loading...' : `${passed} stock(s) cleared the bar`}
        </p>
        {usingMock && !loading && (
          <p className="mt-2 rounded border border-signal-gold/40 bg-signal-gold/10 px-3 py-1.5 font-mono text-[11px] text-signal-gold">
            Showing placeholder data \u2014 couldn&apos;t load latest_screen.json
            from GitHub yet. Has the daily workflow run at least once since
            this JSON output was added?
          </p>
        )}
      </header>

      {loading ? (
        <div className="rounded-lg border border-base-border bg-base-surface p-8 text-center">
          <p className="font-mono text-sm text-ink-muted">Loading...</p>
        </div>
      ) : passed === 0 ? (
        <div className="rounded-lg border border-base-border bg-base-surface p-8 text-center">
          <p className="font-mono text-sm text-ink-muted">
            No stocks cleared the bar today. That&apos;s normal, not a bug.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results!.map((stock) => (
            <StockCard key={stock.ticker} stock={stock} />
          ))}
        </div>
      )}

      <p className="mt-8 border-t border-base-border pt-4 font-mono text-[11px] leading-relaxed text-ink-faint">
        Mechanical rule-based screen, not financial advice. Not a
        SEBI-registered adviser.
      </p>
    </main>
  );
}
