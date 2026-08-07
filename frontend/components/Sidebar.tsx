'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: '\u25a4', ready: true },
  { href: '/scanner', label: 'Scanner', icon: '\u25c9', ready: false },
  { href: '/portfolio', label: 'Portfolio', icon: '\u25c8', ready: false },
  { href: '/alerts', label: 'Alerts', icon: '\u25b2', ready: false },
  { href: '/reports', label: 'Reports', icon: '\u2261', ready: false },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-base-border bg-base-surface">
      <div className="flex items-center gap-2 border-b border-base-border px-5 py-5">
        <span className="font-mono text-lg font-bold tracking-tight text-signal-green">
          NSE
        </span>
        <span className="font-mono text-xs text-ink-muted">AI DASHBOARD</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;

          // Pages that don't exist yet render as disabled, not as a link -
          // shipping a nav item that 404s is worse than one that's honest
          // about not being built.
          if (!item.ready) {
            return (
              <div
                key={item.href}
                className="flex cursor-not-allowed items-center justify-between rounded-md px-3 py-2 text-sm text-ink-faint"
                title="Not built yet"
              >
                <span className="flex items-center gap-3">
                  <span className="w-4 text-center text-xs">{item.icon}</span>
                  {item.label}
                </span>
                <span className="text-[9px] uppercase tracking-wide">soon</span>
              </div>
            );
          }

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                active
                  ? 'bg-base-surface2 text-ink-primary'
                  : 'text-ink-muted hover:bg-base-surface2 hover:text-ink-primary'
              }`}
            >
              <span className="w-4 text-center text-xs">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-base-border px-5 py-4">
        <p className="font-mono text-[11px] leading-relaxed text-ink-faint">
          Rule-based screen.
          <br />
          Not financial advice.
        </p>
      </div>
    </aside>
  );
}
