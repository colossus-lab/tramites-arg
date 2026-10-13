import type { Metadata } from 'next';
import Link from 'next/link';
import FadeIn from '@/components/FadeIn';
import { Barras } from '@/components/Grafico';
import Seccion, { Escala } from '@/components/Seccion';
import Treemap from '@/components/Treemap';
import { agregados, contables } from '@/lib/datos';
import { AUTENTICACION, DESTINATARIOS, MODALIDADES, fecha, monto, num, pct } from '@/lib/formato';

export const metadata: Metadata = {
  title: 'Análisis',
  description: 'Cómo se distribuyen los trámites del Estado Nacional argentino por organismo, categoría, canal, forma de identificarse y costo.',
  alternates: { canonical: '/analisis' },
};

export default function PaginaAnalisis() {
  const a = agregados();
  const t = a.totales;
  const lista = contables();

  const modalidades = new Map<string, number>();
  for (const x of lista) {
    for (const m of new Set(x.canales.map((c) => c.modalidad))) modalidades.set(m, (modalidades.get(m) ?? 0) + 1);
  }
  const sinCanal = lista.filter((x) => x.canales.length === 0).length;

  return (
    <>
      <div className="ed-container">
        <header className="ta-cabecera">
          <p className="ed-eyebrow"><span className="ed-eyebrow-num">Análisis</span><span>Etapa 1 · Estado Nacional</span></p>
          <h1 className="ed-display">Cómo son los trámites del Estado Nacional.</h1>
          <p className="ed-lead">
            {num(t.tramites)} trámites vigentes. Los porcentajes se calculan sobre ese total, sin contar variantes,
            bajas ni trámites de prueba. Ver la <Link href="/metodologia" className="ta-enlace">metodología</Link>.
          </p>
        </header>
      </div>

      <Seccion numero="I." eyebrow="Temas" titulo={<>Trámites <em>por categoría.</em></>}
               bajada="Clasificación automática por organismo, palabras del nombre y etiquetas de TAD, más la curada a mano para los trámites más usados.">
        <FadeIn direction="up" distance={8} duration={0.5}>
          <Barras colorear datos={a.por_categoria.map((c) => ({ etiqueta: c.nombre, valor: c.tramites }))} etiquetaAncho={250} />
        </FadeIn>
      </Seccion>

      <Seccion numero="II." eyebrow="Quién atiende" titulo={<>Trámites <em>por ministerio y organismo.</em></>}>
        <FadeIn direction="up" distance={8} duration={0.5}>
          <Treemap titulo="Trámites por ministerio" maximo={11}
                   items={a.por_ministerio.map((x) => ({ clave: x.slug, etiqueta: x.sigla ?? x.nombre, detalle: x.nombre,
                                                         valor: x.tramites, href: `/organismos/${x.slug}` }))} />
        </FadeIn>
        <div className="ta-panel" style={{ marginTop: '3.5rem' }}>
          <h3>Los 20 organismos con más trámites</h3>
          <p>Contando cada organismo por separado (sin sumar sus dependencias).</p>
          <Barras datos={a.por_organismo.slice(0, 20).map((x) => ({ etiqueta: x.sigla ?? x.nombre, valor: x.tramites }))} etiquetaAncho={160} />
        </div>
      </Seccion>

      <Seccion numero="III." eyebrow="Digitalización" titulo={<>Por dónde <em>se hacen.</em></>}
               bajada="Un trámite puede tener más de un canal: por eso los porcentajes suman más de cien.">
        <div className="ta-grilla-2">
          <div className="ta-panel">
            <h3>Modalidad</h3>
            <p>{num(sinCanal)} trámites no informan cómo se hacen.</p>
            <Barras datos={[...modalidades.entries()].sort((x, y) => y[1] - x[1])
              .map(([m, v]) => ({ etiqueta: MODALIDADES[m] ?? m, valor: v }))} etiquetaAncho={110} />
          </div>
          <div className="ta-panel">
            <h3>Plataforma</h3>
            <p>Dónde se inicia el trámite en línea.</p>
            <Barras datos={a.por_plataforma.map((p) => ({ etiqueta: p.plataforma.replace(/\s*\(.*\)$/, ''), valor: p.tramites }))}
                    etiquetaAncho={190} />
          </div>
          <div className="ta-panel">
            <h3>Cómo te identificás</h3>
            <p>Métodos aceptados para iniciar el trámite (puede haber varios).</p>
            <Barras datos={a.autenticacion.filter((x) => x.metodo !== 'otro')
              .map((x) => ({ etiqueta: AUTENTICACION[x.metodo] ?? x.metodo, valor: x.tramites }))} etiquetaAncho={230} />
          </div>
          <div className="ta-panel">
            <h3>Para quién</h3>
            <p>Destinatarios identificados en {pct(t.con_destinatario_pct)} de los trámites.</p>
            <Barras datos={a.por_destinatario.map((x) => ({ etiqueta: DESTINATARIOS[x.tipo] ?? x.tipo, valor: x.tramites }))}
                    etiquetaAncho={190} />
          </div>
        </div>
      </Seccion>

      <Seccion numero="IV." eyebrow="Costos" titulo={<>Cuánto <em>cuestan.</em></>}
               bajada="El costo sale del catálogo de TAD, de la descripción de cada trámite, de las fichas de argentina.gob.ar y del relevamiento propio.">
        <Escala filas={[
          { n: num(a.costos.arancelados), label: 'Trámites con costo', detail: `${pct(t.arancelados_pct)} del total.` },
          { n: num(a.costos.gratuitos), label: 'Informados como gratuitos', detail: 'Ninguna fuente menciona un costo.' },
          { n: num(a.costos.subestimados_csv_tad), label: '“No arancelados” que piden pagar', detail: 'El catálogo de TAD los marca sin arancel, pero la descripción o la ficha informan un monto.' },
          { n: a.costos.mediana ? monto(a.costos.mediana, 'ARS') : '—', label: 'Arancel mediano', detail: 'Entre los trámites con un monto en pesos informado.' },
        ]} />
        <div className="ta-grilla-2" style={{ marginTop: '3rem' }}>
          <div className="ta-panel">
            <h3>Distribución de los aranceles</h3>
            <p>Monto máximo informado de cada trámite con costo en pesos.</p>
            <Barras horizontal={false} datos={a.costos.distribucion.map((d) => ({ etiqueta: d.tramo, valor: d.tramites }))} />
          </div>
          <div className="ta-panel">
            <h3>Montos que no coinciden</h3>
            <p>Trámites en los que el catálogo de TAD y otra fuente informan aranceles distintos.</p>
            {a.costos.discrepancias.length ? (
              <div className="ta-tabla-scroll">
                <table className="ta-tabla">
                  <thead><tr><th>Trámite</th><th>Catálogo TAD</th><th>Otra fuente</th></tr></thead>
                  <tbody>
                    {a.costos.discrepancias.slice(0, 12).map((d) => (
                      <tr key={`${d.slug}-${d.otra_fuente}`}>
                        <td><Link href={`/tramites/${d.slug}`} className="ta-enlace">{d.nombre}</Link></td>
                        <td className="ta-num">{monto(d.csv, 'ARS')}</td>
                        <td className="ta-num">{monto(d.otra_fuente, 'ARS')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="ta-nota">No se encontraron diferencias.</p>}
          </div>
        </div>
      </Seccion>

      <Seccion numero="V." eyebrow="Requisitos" titulo={<>Qué <em>se pide.</em></>}
               bajada={`Documentos más mencionados en los requisitos. Hay requisitos detallados para ${pct(t.con_requisitos_pct)} de los trámites: en el resto, los documentos se piden dentro del formulario de cada plataforma.`}>
        <Barras colorear datos={a.requisitos_top.map((r) => ({ etiqueta: r.documento, valor: r.tramites }))} etiquetaAncho={260} />
      </Seccion>

      <Seccion numero="VI." eyebrow="En el tiempo" titulo={<>Cuándo llegaron <em>a TAD.</em></>}
               bajada="Año de publicación de cada trámite vigente en la plataforma de Trámites a Distancia.">
        <Barras horizontal={false} datos={a.por_anio_publicacion_tad.map((x) => ({ etiqueta: x.anio, valor: x.tramites }))} />
      </Seccion>

      <Seccion numero="VII." eyebrow="Cambios institucionales" titulo={<>Organismos que <em>cambiaron.</em></>}
               bajada="Disoluciones y reemplazos que afectan a qué organismo atiende cada trámite.">
        <div className="ta-tabla-scroll">
          <table className="ta-tabla">
            <thead><tr><th>Antes</th><th>Ahora</th><th>Desde</th><th>Norma</th><th>Trámites hoy</th></tr></thead>
            <tbody>
              {a.cambios_institucionales.map((c) => (
                <tr key={c.anterior}>
                  <td>{c.anterior}{c.anterior_sigla && ` (${c.anterior_sigla})`}</td>
                  <td><Link href={`/organismos/${c.sucesor_slug}`} className="ta-enlace">{c.sucesor}{c.sucesor_sigla && ` (${c.sucesor_sigla})`}</Link></td>
                  <td className="ta-num">{fecha(c.fecha)}</td>
                  <td>{c.norma ?? '—'}</td>
                  <td className="ta-num">{num(c.tramites)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Seccion>

      <Seccion numero="VIII." eyebrow="Cobertura" titulo={<>Qué tan completos <em>están los datos.</em></>}>
        <Escala filas={[
          { n: pct(t.con_categoria_pct), label: 'Con categoría', detail: 'Asignada a mano o por reglas automáticas.' },
          { n: pct(t.con_destinatario_pct), label: 'Con destinatario', detail: 'Personas, empresas, profesionales, organizaciones u organismos públicos.' },
          { n: pct(t.con_requisitos_pct), label: 'Con requisitos detallados', detail: 'Extraídos de la descripción o de la ficha oficial.' },
          { n: pct(100 - t.costo_sin_dato_pct), label: 'Con dato de costo', detail: 'Gratuito o con un arancel informado.' },
        ]} />
      </Seccion>
    </>
  );
}
