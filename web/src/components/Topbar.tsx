'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import ThemeToggle from './ThemeToggle';

const LINKS = [
  { href: '/tramites', label: 'Trámites' },
  { href: '/organismos', label: 'Organismos' },
  { href: '/analisis', label: 'Análisis' },
  { href: '/metodologia', label: 'Metodología' },
];

export default function Topbar() {
  const pathname = usePathname();
  return (
    <header className="ed-topbar">
      <Link href="/" className="ed-topbar-mark" aria-label="Trámites Arg, ir al inicio">
        <span className="ed-topbar-mark-name">Trámites Arg</span>
        <span className="ed-topbar-mark-sub">por Colossus Lab</span>
      </Link>

      <nav className="ed-topbar-nav" aria-label="Navegación principal">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={pathname?.startsWith(l.href) ? 'is-active' : ''}>
            {l.label}
          </Link>
        ))}
      </nav>

      <div className="ed-topbar-right">
        <ThemeToggle />
        <Link href="/datos" className="ed-topbar-cta">
          Datos abiertos <span aria-hidden="true">→</span>
        </Link>
      </div>
    </header>
  );
}
