import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { Barras } from '@/components/Grafico';
import { Escala } from '@/components/Seccion';
import { descendientes, jerarquia, tramitesDe } from '@/lib/organismos';
import { MODALIDADES, fecha, num, pct } from '@/lib/formato';

export const dynamicParams = false;

export function generateStaticParams() {
  const { porSlug } = jerarquia();
  return [...porSlug.values()].filter((n) => n.total > 0 || n.sucesor).map((n) => ({ slug: n.slug }));
}

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const n = jerarquia().porSlug.get((await params).slug);
  if (!n) return {};
  return {
    title: n.sigla ? `${n.nombre} (${n.sigla})` : n.nombre,
    description: `Trámites de ${n.nombre}: cuántos son, cómo se hacen y cuánto cuestan.`,
    alternates: { canonical: `/organismos/${n.slug}` },
  };
}

export default async function PaginaOrganismo({ params }: Props) {
  const { porSlug } = jerarquia();
  const n = porSlug.get((await params).slug);
  if (!n) notFound();

  const padres = [];
  for (let p = n.padre ? porSlug.get(n.padre) : undefined; p; p = p.padre ? porSlug.get(p.padre) : undefined) padres.unshift(p);
  const sucesor = n.sucesor ? porSlug.get(n.sucesor) : undefined;
  const antecesores = [...porSlug.values()].filter((o) => o.sucesor === n.slug);
  const lista = tramitesDe(n).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  const total = lista.length;
  const online = lista.filter((t) => t.canales.some((c) => c.modalidad === 'online' || c.modalidad === 'mixta')).length;
  const conCosto = lista.filter((t) => t.costos.some((c) => !c.gratuito)).length;
  const conRequisitos = lista.filter((t) => t.requisitos.length > 0).length;

  const porCategoria = new Map<string, number>();
  for (const t of lista) {
    const k = t.categoria?.nombre ?? 'Sin categoría';
    porCategoria.set(k, (porCategoria.get(k) ?? 0) + 1);
  }
  const categorias = [...porCategoria.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10)
    .map(([etiqueta, valor]) => ({ etiqueta, valor }));
  const dependencias = descendientes(n).filter((d) => d.total > 0);
  const porOrganismo = new Map<string, typeof lista>();
  for (const t of lista) porOrganismo.set(t.organismo.slug, [...(porOrganismo.get(t.organismo.slug) ?? []), t]);

  return (
    <div className="ed-container">
      <header className="ta-cabecera">
        <nav className="ta-migas" aria-label="Ubicación">
          <Link href="/organismos">Organismos</Link>
          {padres.map((p) => (<span key={p.slug}><span aria-hidden="true">/ </span><Link href={`/organismos/${p.slug}`}>{p.sigla ?? p.nombre}</Link></span>))}
        </nav>
        <h1 className="ed-display">{n.nombre}</h1>
        <div className="ta-etiquetas">
          {n.sigla && <span className="ta-etiqueta ta-etiqueta--celeste">{n.sigla}</span>}
          {n.tipo && <span className="ta-etiqueta">{n.tipo.replaceAll('_', ' ')}</span>}
          {n.vigente_hasta && <span className="ta-etiqueta ta-etiqueta--baja">Disuelto el {fecha(n.vigente_hasta)}</span>}
        </div>
        {sucesor && (
          <p className="ta-aviso">
            Este organismo fue reemplazado por <Link href={`/organismos/${sucesor.slug}`} className="ta-enlace">{sucesor.nombre}</Link>
            {n.norma_disolucion && <> ({n.norma_disolucion})</>}. Sus trámites figuran en el sucesor.
          </p>
        )}
        {antecesores.length > 0 && (
          <p className="ta-nota">Antes: {antecesores.map((a) => `${a.nombre}${a.sigla ? ` (${a.sigla})` : ''}`).join(', ')}.
            {n.norma_creacion && <> Creado por {n.norma_creacion}.</>}</p>
        )}
      </header>

      {total > 0 && (
        <>
          <section className="ed-section">
            <Escala filas={[
              { n: num(total), label: 'Trámites vigentes', detail: dependencias.length ? `Incluye ${num(dependencias.length)} organismos dependientes.` : 'Atendidos directamente por este organismo.' },
              { n: pct((online / total) * 100), label: 'Se inician en línea', detail: `${num(online)} de ${num(total)} trámites.` },
              { n: pct((conCosto / total) * 100), label: 'Tienen costo', detail: `${num(conCosto)} trámites con un arancel informado.` },
              { n: pct((conRequisitos / total) * 100), label: 'Con requisitos detallados', detail: 'Extraídos de la descripción o de la ficha oficial.' },
            ]} />
          </section>

          <section className="ta-grilla-2" style={{ padding: '1rem 0 3rem' }}>
            <div className="ta-panel">
              <h3>Por categoría</h3>
              <p>Clasificación temática de los trámites.</p>
              <Barras datos={categorias} etiquetaAncho={170} />
            </div>
            {dependencias.length > 0 && (
              <div className="ta-panel">
                <h3>Organismos dependientes</h3>
                <p>Cantidad de trámites de cada uno.</p>
                <ul className="ta-lista">
                  {dependencias.map((d) => (
                    <li key={d.slug} style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
                      <Link href={`/organismos/${d.slug}`} className="ta-enlace">{d.sigla ?? d.nombre}</Link>
                      <span className="ed-meta-mono">{num(d.total)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="ta-bloque" style={{ paddingBottom: '4rem' }}>
            <h2>Trámites</h2>
            {[...porOrganismo.entries()].map(([slug, grupo]) => (
              <div key={slug}>
                {porOrganismo.size > 1 && <h3>{porSlug.get(slug)?.nombre}</h3>}
                <ul className="ta-resultados" style={{ marginTop: '0.5rem' }}>
                  {grupo.map((t) => (
                    <li key={t.slug} className="ta-resultado">
                      <Link href={`/tramites/${t.slug}`}>
                        <span className="ta-resultado-nombre">{t.nombre}</span>
                        <span className="ta-resultado-org">{t.categoria?.nombre ?? ''}</span>
                        <span className="ta-etiquetas">
                          {[...new Set(t.canales.map((c) => c.modalidad))].map((m) => (
                            <span key={m} className="ta-etiqueta ta-etiqueta--celeste">{MODALIDADES[m] ?? m}</span>))}
                          {t.costos.some((c) => !c.gratuito) && <span className="ta-etiqueta ta-etiqueta--acento">Con costo</span>}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
