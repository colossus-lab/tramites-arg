import type { Metadata } from 'next';
import Link from 'next/link';
import { descendientes, jerarquia } from '@/lib/organismos';
import { num } from '@/lib/formato';

export const metadata: Metadata = {
  title: 'Organismos',
  description: 'Los organismos del Estado Nacional argentino que atienden trámites, agrupados por ministerio.',
  alternates: { canonical: '/organismos' },
};

export default function PaginaOrganismos() {
  const { raices } = jerarquia();
  const conTramites = raices.filter((r) => r.total > 0);
  const anteriores = raices.filter((r) => r.total === 0 && r.sucesor);
  return (
    <div className="ed-container">
      <header className="ta-cabecera">
        <p className="ed-eyebrow"><span className="ed-eyebrow-num">Índice</span><span>Organismos</span></p>
        <h1 className="ed-display">Quién atiende cada trámite.</h1>
        <p className="ed-lead">
          {num(conTramites.length)} ministerios, secretarías y entes de primer nivel, con sus organismos dependientes.
          El número es la cantidad de trámites vigentes, incluidos los de sus dependencias.
        </p>
      </header>

      <div className="ta-organismos" style={{ padding: '3rem 0 4rem' }}>
        {conTramites.map((r) => (
          <section key={r.slug} className="ta-ministerio">
            <h2><Link href={`/organismos/${r.slug}`}>{r.nombre}</Link> <span className="ed-meta-mono">{num(r.total)}</span></h2>
            <ul>
              {r.tramites > 0 && r.hijos.length > 0 && (
                <li><Link href={`/organismos/${r.slug}`}>Trámites del propio ministerio</Link><span>{num(r.tramites)}</span></li>
              )}
              {descendientes(r).filter((d) => d.total > 0).map((d) => (
                <li key={d.slug}>
                  <Link href={`/organismos/${d.slug}`}>{d.sigla ? `${d.nombre} (${d.sigla})` : d.nombre}</Link>
                  <span>{num(d.total)}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {anteriores.length > 0 && (
        <section className="ta-bloque" style={{ paddingBottom: '4rem' }}>
          <h2>Organismos que cambiaron de nombre o fueron absorbidos</h2>
          <ul className="ta-lista">
            {anteriores.map((o) => (
              <li key={o.slug}>
                {o.nombre}{o.sigla && ` (${o.sigla})`} → <Link className="ta-enlace" href={`/organismos/${o.sucesor}`}>sucesor</Link>
                <span className="ta-lista-meta">{[o.norma_disolucion, o.vigente_hasta && `hasta ${o.vigente_hasta}`].filter(Boolean).join(' · ')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
