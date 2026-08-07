import { StockResult } from '@/components/StockCard';

// Placeholder data shaped exactly like swing_trade_screener.py's real output.
// Once the backend's /api/screener/latest endpoint exists (a later sprint),
// this file goes away and the dashboard fetches real results instead.
export const MOCK_RESULTS: StockResult[] = [
  {
    ticker: 'SBIN', score: 8, max_score: 9, close: 812.4, rsi: 58.2,
    pe: 11.8, roe_pct: 17.4, debt_to_equity: 0.62,
    stop_loss: 782.1, target: 873.0, reward_risk: 2.0,
  },
  {
    ticker: 'PNB', score: 7, max_score: 9, close: 118.6, rsi: 61.5,
    pe: 9.4, roe_pct: 14.1, debt_to_equity: 0.88,
    stop_loss: 112.3, target: 131.2, reward_risk: 2.0,
  },
  {
    ticker: 'GAIL', score: 7, max_score: 9, close: 214.9, rsi: 55.0,
    pe: 13.2, roe_pct: 15.6, debt_to_equity: 0.24,
    stop_loss: 205.4, target: 233.9, reward_risk: 2.0,
  },
  {
    ticker: 'TATAPOWER', score: 6, max_score: 9, close: 442.1, rsi: 49.8,
    pe: 28.6, roe_pct: 12.9, debt_to_equity: 1.05,
    stop_loss: 421.0, target: 484.3, reward_risk: 2.0,
  },
];

export const MOCK_META = {
  runDate: '06 Aug 2026, 09:00 IST',
  totalScreened: 75,
  maxPrice: 1000,
};
