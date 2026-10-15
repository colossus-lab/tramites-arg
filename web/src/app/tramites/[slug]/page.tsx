import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { tramite, tramites } from '@/lib/datos';
import type { Costo, Requisito, Tramite } from '@/lib/tipos';
import {
  AUTENTICACION, DESTINATARIOS, ESTADOS, FUENTES, MODALIDADES, SITIO, TIPO_REQUISITO, fecha, monto,
} from '@/lib/formato';

export const dynamicParams = false;

export function generateStaticParams() {
  return tramites().map((t) => ({ slug: t.slug }));
}

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const t = tramite((await params).slug);
  if (!t) return {};
  const organismo = t.organismo.sigla ?? t.organismo.nombre;
  return {
    title: t.nombre,
    description: t.descripcion ?? `${t.nombre}: organismo, requisitos, costo y cómo hacerlo (${organismo}).`,
    alternates: { canonical: `/tramites/${t.slug}` },
  };
}

const SECCIONES_FICHA: [string, string][] = [
  ['dirigido', '¿A quién está dirigido?'], ['necesito', '¿Qué necesito?'], ['como', '¿Cómo hago?'],
  ['costo', '¿Cuál es el costo?'], ['tiempo', '¿Cuánto tiempo lleva?'], ['vigencia', 'Vigencia'],
];

function agrupar<T>(items: T[], clave: (x: T) => string): [string, T[]][] {
  const mapa = new Map<string, T[]>();
  for (const x of items) {
    const k = clave(x);
    mapa.set(k, [...(mapa.get(k) ?? []), x]);
  }
  return [...mapa.entries()];
}

function textoCosto(c: Costo): string {
  if (c.gratuito) return 'Gratuito';
  if (c.monto_min == null && c.monto_max == null) return 'Con costo (monto no informado)';
  if (c.monto_min != null && c.monto_max != null && c.monto_min !== c.monto_max) {
    return `${monto(c.monto_min, c.unidad)} a ${monto(c.monto_max, c.unidad)}`;
  }
  return monto(c.monto_max ?? c.monto_min, c.unidad);
}

function hayDiscrepancia(t: Tramite): boolean {
  const montos = new Set(
    t.costos.filter((c) => !c.gratuito && c.monto_max != null && c.unidad === 'ARS' && !c.variante).map((c) => c.monto_max),
  );
  return montos.size > 1;
}

function Requisitos({ items }: { items: Requisito[] }) {
  return (
    <>
      {agrupar(items, (r) => `${r.fuente}|${r.seccion ?? ''}`).map(([clave, grupo]) => {
        const [fuente, seccion] = clave.split('|');
        return (
          <div key={clave}>
            <h3>{seccion || 'Requisitos'} <span className="ta-lista-meta" style={{ display: 'inline' }}>· según {FUENTES[fuente] ?? fuente}</span></h3>
            <ul className="ta-lista">
              {grupo.map((r, i) => (
                <li key={i}>
                  {r.previo ? <Link href={`/tramites/${r.previo}`} className="ta-enlace">{r.descripcion}</Link> : r.descripcion}
                  <span className="ta-lista-meta">
                    {TIPO_REQUISITO[r.tipo] ?? r.tipo}{!r.obligatorio && ' · opcional'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </>
  );
}

export default async function PaginaTramite({ params }: Props) {
  const t = tramite((await params).slug);
  if (!t) notFound();

  const tad = t.fuentes.find((f) => f.tipo === 'tad');
  const ficha = t.fuentes.find((f) => f.tipo === 'ficha');
  const ministerio = t.organismo.ministerio;
  const tituloIssue = encodeURIComponent(`Corrección en "${t.nombre}"`);
  const cuerpoIssue = encodeURIComponent(`Trámite: ${SITIO.url}/tramites/${t.slug}\n\nQué está mal:\n\nFuente oficial que lo respalda:\n`);

  return (
    <div className="ed-container">
      <header className="ta-cabecera">
        <nav className="ta-migas" aria-label="Ubicación">
          <Link href="/tramites">Trámites</Link><span aria-hidden="true">/</span>
          {ministerio && (<><Link href={`/organismos/${ministerio.slug}`}>{ministerio.sigla ?? ministerio.nombre}</Link><span aria-hidden="true">/</span></>)}
          <Link href={`/organismos/${t.organismo.slug}`}>{t.organismo.sigla ?? t.organismo.nombre}</Link>
        </nav>
        <h1 className="ed-display">{t.nombre}</h1>
        {t.descripcion && <p className="ed-lead">{t.descripcion}</p>}
        <div className="ta-etiquetas">
          {t.estado !== 'vigente' && <span className="ta-etiqueta ta-etiqueta--baja">{ESTADOS[t.estado]}</span>}
          {t.naturaleza === 'consulta' && <span className="ta-etiqueta">Servicio de consulta</span>}
          {t.categoria && <span className="ta-etiqueta">{t.categoria.nombre}</span>}
          {[...new Set(t.canales.map((c) => c.modalidad))].map((m) => (
            <span key={m} className="ta-etiqueta ta-etiqueta--celeste">{MODALIDADES[m] ?? m}</span>
          ))}
          {t.destinatarios.map((d) => <span key={d} className="ta-etiqueta">{DESTINATARIOS[d] ?? d}</span>)}
        </div>
        {t.estado === 'baja' && (
          <p className="ta-aviso">
            Este trámite fue dado de baja.
            {t.reemplazado_por && <> Ahora se hace con <Link href={`/tramites/${t.reemplazado_por}`} className="ta-enlace">otro trámite</Link>.</>}
          </p>
        )}
        {t.prueba && <p className="ta-aviso">Figura en el catálogo oficial de TAD pero parece ser un trámite de prueba de la plataforma.</p>}
        {t.naturaleza === 'consulta' && (
          <p className="ta-aviso">
            Es un servicio de consulta: permite ver información sin pedirle nada al organismo, así que no se cuenta
            como trámite en los análisis.
          </p>
        )}
      </header>

      <div className="ta-ficha">
        <article>
          {t.canales.length > 0 && (
            <section className="ta-bloque">
              <h2>Cómo se hace</h2>
              <ul className="ta-lista">
                {t.canales.map((c, i) => (
                  <li key={i}>
                    <strong>{MODALIDADES[c.modalidad] ?? c.modalidad}</strong>
                    {c.plataforma_nombre && <> · {c.plataforma_nombre}</>}
                    {c.detalle && <> · {c.detalle}</>}
                    {c.requiere_turno && <> · con turno</>}
                    {c.autenticacion.length > 0 && (
                      <span className="ta-lista-meta">Te identificás con: {c.autenticacion.map((m) => AUTENTICACION[m] ?? m).join(', ')}</span>
                    )}
                    {c.url && (
                      <span className="ta-lista-meta">
                        <a href={c.url} className="ta-enlace" target="_blank" rel="noopener nofollow">Ir al sitio oficial ↗</a>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {t.requisitos.length > 0 && (
            <section className="ta-bloque">
              <h2>Qué se necesita</h2>
              <Requisitos items={t.requisitos} />
              <p className="ta-nota">Extraído automáticamente de las fuentes oficiales: puede estar incompleto. Verificá en la fuente antes de iniciar el trámite.</p>
            </section>
          )}

          {t.costos.length > 0 && (
            <section className="ta-bloque">
              <h2>Cuánto cuesta</h2>
              {hayDiscrepancia(t) && (
                <p className="ta-aviso">Las fuentes informan montos distintos para este trámite. Confirmá el valor vigente en la fuente oficial.</p>
              )}
              <div className="ta-tabla-scroll">
                <table className="ta-tabla">
                  <thead><tr><th>Concepto</th><th>Monto</th><th>Norma</th><th>Fuente</th></tr></thead>
                  <tbody>
                    {t.costos.map((c, i) => (
                      <tr key={i}>
                        <td>{c.variante ? `${c.variante}` : c.concepto}{c.detalle && <span className="ta-lista-meta">{c.detalle}</span>}</td>
                        <td className="ta-num">{textoCosto(c)}</td>
                        <td>{c.norma ?? '—'}</td>
                        <td>{FUENTES[c.fuente] ?? c.fuente}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {t.costos.some((c) => c.unidad === 'UMSM') && (
                <p className="ta-nota">UMSM: Unidad Móvil del Sistema Migratorio; su valor en pesos lo fija la Dirección Nacional de Migraciones.</p>
              )}
            </section>
          )}

          {t.variantes.length > 0 && (
            <section className="ta-bloque">
              <h2>Variantes</h2>
              <ul className="ta-lista">
                {t.variantes.map((v) => (
                  <li key={v.nombre}>
                    {v.nombre}
                    {v.id_tad && (
                      <span className="ta-lista-meta">
                        <a className="ta-enlace" target="_blank" rel="noopener nofollow"
                           href={`https://tramitesadistancia.gob.ar/tramitesadistancia/detalle-tipo?id=${v.id_tad}`}>
                          Trámite {v.id_tad} en TAD ↗
                        </a>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {(t.descripciones.ficha || t.descripciones.tad) && (
            <section className="ta-bloque">
              <h2>Información oficial</h2>
              {t.descripciones.ficha && SECCIONES_FICHA.filter(([k]) => t.descripciones.ficha?.[k]).map(([k, titulo]) => (
                <details key={k} className="ta-desplegable" open={k === 'necesito'}>
                  <summary>{titulo}</summary>
                  <div className="ta-html" dangerouslySetInnerHTML={{ __html: t.descripciones.ficha?.[k] ?? '' }} />
                </details>
              ))}
              {t.descripciones.tad && (
                <details className="ta-desplegable" open={!t.descripciones.ficha}>
                  <summary>Descripción en Trámites a Distancia</summary>
                  <div className="ta-html" dangerouslySetInnerHTML={{ __html: t.descripciones.tad }} />
                </details>
              )}
              <p className="ta-nota">Texto copiado de las fuentes oficiales al {fecha(t.fecha_verificacion)}.</p>
            </section>
          )}
        </article>

        <aside className="ta-ficha-aside" aria-label="Datos del trámite">
          <dl className="ta-dato">
            <dt>Organismo</dt>
            <dd><Link href={`/organismos/${t.organismo.slug}`} className="ta-enlace">{t.organismo.nombre}</Link></dd>
          </dl>
          {ministerio && (
            <dl className="ta-dato"><dt>Depende de</dt>
              <dd><Link href={`/organismos/${ministerio.slug}`} className="ta-enlace">{ministerio.nombre}</Link></dd></dl>
          )}
          {t.categoria && (
            <dl className="ta-dato"><dt>Categoría</dt>
              <dd>{t.categoria.nombre}
                {t.categoria_confianza === 'baja' && <span className="ta-lista-meta">Clasificación automática de baja confianza</span>}
              </dd></dl>
          )}
          {t.destinatarios.length > 0 && (
            <dl className="ta-dato"><dt>Para</dt><dd>{t.destinatarios.map((d) => DESTINATARIOS[d] ?? d).join(', ')}</dd></dl>
          )}
          {t.fecha_publicacion_tad && (
            <dl className="ta-dato"><dt>En TAD desde</dt><dd>{fecha(t.fecha_publicacion_tad)}</dd></dl>
          )}
          {t.norma && <dl className="ta-dato"><dt>Norma</dt><dd>{t.norma}</dd></dl>}
          <dl className="ta-dato">
            <dt>Fuentes oficiales</dt>
            <dd>
              {tad?.url && <a href={tad.url} className="ta-enlace" target="_blank" rel="noopener nofollow">Trámites a Distancia (n.º {tad.id}) ↗</a>}
              {ficha?.url && <><br /><a href={ficha.url} className="ta-enlace" target="_blank" rel="noopener nofollow">Ficha en argentina.gob.ar ↗</a></>}
              {t.fuentes.some((f) => f.tipo === 'inventario') && (
                <><br /><span>Relevamiento propio ({t.fuentes.find((f) => f.tipo === 'inventario')?.id})</span></>
              )}
              <span className="ta-lista-meta">Verificado al {fecha(t.fecha_verificacion ?? t.fuentes[0]?.capturado)}</span>
            </dd>
          </dl>
          <dl className="ta-dato">
            <dt>¿Algo está mal?</dt>
            <dd>
              <a className="ta-enlace" target="_blank" rel="noopener noreferrer"
                 href={`${SITIO.repo}/issues/new?title=${tituloIssue}&body=${cuerpoIssue}`}>Reportalo en GitHub ↗</a>
            </dd>
          </dl>
        </aside>
      </div>
    </div>
  );
}
