'use client';

// Adaptado de HeroEditorial de OpenArg (github.com/colossus-lab/openarg_frontend, MIT).

import { useState } from 'react';
import Link from 'next/link';
import FadeIn from './FadeIn';

const TOC = [
  { label: 'I. La escala', href: '#escala' },
  { label: 'II. Quién atiende', href: '#organismos' },
  { label: 'III. Hallazgos', href: '#hallazgos' },
  { label: 'IV. De dónde salen los datos', href: '#fuentes' },
];

const CTAS = [
  { href: '/tramites', label: 'Buscar un trámite' },
  { href: '/analisis', label: 'Ver el análisis' },
  { href: '/metodologia', label: 'Cómo se armó' },
];

export default function Hero({ total, organismos, fechaCorte }: { total: string; organismos: string; fechaCorte: string }) {
  const [menuAbierto, setMenuAbierto] = useState(false);
  return (
    <section className="ed-hero">
      <span className="ed-flagstripe" aria-hidden="true" />
      <div className="ed-container ed-hero-inner">
        <div className="ed-hero-center">
          <FadeIn direction="up" distance={8} duration={0.5}>
            <p className="ed-eyebrow ed-hero-eyebrow-center">
              <span className="ed-eyebrow-num">Etapa 1 / MMXXVI</span>
              <span>Estado Nacional argentino</span>
            </p>
          </FadeIn>
          <FadeIn direction="up" distance={10} delay={0.1} duration={0.6}>
            <h1 className="ed-display ed-hero-title">
              <span className="ed-hero-title-line">Argentina,</span>
              <span className="ed-hero-title-line ed-hero-title-line--alt">trámite por trámite.</span>
            </h1>
          </FadeIn>
          <FadeIn direction="up" distance={8} delay={0.25} duration={0.5}>
            <p className="ed-hero-subtitle">
              Qué trámites tiene el Estado Nacional, qué organismo los atiende, cómo se hacen,
              qué piden y cuánto cuestan. En una sola base abierta.
            </p>
          </FadeIn>
          <FadeIn direction="up" distance={8} delay={0.35} duration={0.5}>
            <div className="ed-hero-actions">
              <div className="ed-hero-actions-row">
                {CTAS.map((c) => (
                  <Link key={c.href} href={c.href} className="ed-textlink">
                    <span className="ed-textlink-arrow">→</span>
                    <span>{c.label}</span>
                  </Link>
                ))}
              </div>
              <div className="ed-hero-actions-toggle-wrap">
                <button type="button" className="ed-hero-actions-toggle" onClick={() => setMenuAbierto((v) => !v)}
                        aria-expanded={menuAbierto} aria-controls="ta-hero-menu">
                  <span>Explorar</span>
                  <span className="ed-hero-actions-toggle-chev" aria-hidden="true">▾</span>
                </button>
                <div id="ta-hero-menu" className={`ed-hero-actions-menu${menuAbierto ? ' is-open' : ''}`} role="menu">
                  {CTAS.map((c) => (
                    <Link key={c.href} href={c.href} role="menuitem" onClick={() => setMenuAbierto(false)}>
                      <span>{c.label}</span>
                      <span className="ed-hero-actions-menu-arrow" aria-hidden="true">→</span>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </FadeIn>
        </div>

        <div className="ed-hero-foot">
          <div className="ed-hero-foot-left">
            <FadeIn direction="up" distance={8} delay={0.55} duration={0.5}>
              <div className="ed-num-display ed-hero-num">{total}</div>
            </FadeIn>
            <FadeIn direction="up" distance={8} delay={0.6} duration={0.5}>
              <p className="ed-meta ed-hero-num-label">Trámites vigentes · {organismos} organismos</p>
            </FadeIn>
            <FadeIn direction="up" distance={8} delay={0.65} duration={0.5}>
              <p className="ed-lead">
                Relevados de Trámites a Distancia, de las fichas de argentina.gob.ar y de un inventario
                propio de los trámites más usados.
              </p>
            </FadeIn>
          </div>
          <div className="ed-hero-foot-right">
            <FadeIn direction="up" distance={6} delay={0.7} duration={0.5}>
              <nav className="ed-hero-toc" aria-label="Índice de secciones">
                <ul className="ed-hero-toc-list">
                  {TOC.map((t) => (
                    <li key={t.href}><a href={t.href}>{t.label}</a></li>
                  ))}
                </ul>
              </nav>
            </FadeIn>
            <FadeIn direction="up" distance={6} delay={0.8} duration={0.5}>
              <p className="ed-hero-colophon">
                Colossus Lab · Datos al {fechaCorte}
                <span className="ed-hero-disclaimer"> · Proyecto no oficial</span>
              </p>
            </FadeIn>
          </div>
        </div>
      </div>
    </section>
  );
}
