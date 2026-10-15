import Link from 'next/link';
import FadeIn from '@/components/FadeIn';
import Hero from '@/components/Hero';
import Seccion, { Escala } from '@/components/Seccion';
import Treemap from '@/components/Treemap';
import { agregados, meta } from '@/lib/datos';
import { fecha, num, pct } from '@/lib/formato';

export default function Inicio() {
  const a = agregados();
  const t = a.totales;
  const m = meta();
  const tad = a.por_plataforma.find((p) => p.plataforma.startsWith('Trámites a Distancia'))?.tramites ?? 0;
  const claveFiscal = a.autenticacion.find((x) => x.metodo === 'clave_fiscal')?.tramites ?? 0;
  const primerMinisterio = a.por_ministerio[0];
  const top3 = a.por_ministerio.slice(0, 3).reduce((s, x) => s + x.tramites, 0);
  const destinatario = (tipo: string) => a.por_destinatario.find((x) => x.tipo === tipo)?.tramites ?? 0;
  const empresas = destinatario('empresa');
  const personas = destinatario('pf_ciudadano');

  const hallazgos = [
    {
      n: pct((top3 / t.tramites) * 100),
      titulo: 'de los trámites se concentra en tres ministerios',
      texto: `${primerMinisterio.nombre} encabeza con ${num(primerMinisterio.tramites)} trámites, entre los que atiende el propio ministerio y sus organismos.`,
    },
    {
      n: `${(empresas / Math.max(personas, 1)).toLocaleString('es-AR', { maximumFractionDigits: 1 })} a 1`,
      titulo: 'trámites para empresas por cada uno para personas',
      texto: `${num(empresas)} trámites están dirigidos a empresas y ${num(personas)} a personas. El catálogo nacional es, sobre todo, regulatorio: habilitaciones, registros e inscripciones.`,
    },
    {
      n: pct(t.solo_presencial_pct),
      titulo: 'de los trámites solo se puede hacer en persona',
      texto: `El ${pct(t.online_pct)} se puede iniciar en línea, casi siempre por Trámites a Distancia. Los presenciales salen de las fichas de argentina.gob.ar: oficinas, mesas de entradas y turnos.`,
    },
    {
      n: pct(t.top10_organismos_pct),
      titulo: 'de los trámites los atienden solo diez organismos',
      texto: `Hay ${num(t.organismos)} organismos con al menos un trámite, pero la mayoría tiene muy pocos: la carga se concentra en unos pocos reguladores.`,
    },
    {
      n: pct((claveFiscal / t.tramites) * 100),
      titulo: 'aceptan la clave fiscal de ARCA para identificarse',
      texto: 'Es el método de identificación más aceptado, también en trámites que no son impositivos. Mi Argentina le sigue de cerca.',
    },
    {
      n: num(a.costos.subestimados_csv_tad),
      titulo: 'trámites figuran como “no arancelados” en TAD pero piden pagar',
      texto: 'La marca de arancel del catálogo oficial no siempre coincide con lo que dicen la descripción o la ficha del trámite, donde aparece un monto a pagar.',
    },
  ];

  return (
    <>
      <Hero total={num(t.tramites)} organismos={num(t.organismos)} fechaCorte={fecha(m.fecha_corte)} />

      <Seccion id="escala" numero="I." eyebrow="La escala"
               titulo={<>Cuántos trámites tiene <em>el Estado Nacional.</em></>}
               bajada="Cada trámite es una solicitud con un resultado distinto ante un organismo. Las variantes de precio, plazo o tipo de persona no se cuentan aparte.">
        <Escala filas={[
          { n: num(t.tramites), label: 'Trámites vigentes', detail: `Sin contar ${num(t.variantes)} variantes, ${num(t.bajas)} bajas, ${num(t.prueba)} trámites de prueba ni ${num(t.consultas)} servicios de consulta.` },
          { n: num(t.organismos), label: 'Organismos', detail: `Agrupados en ${num(t.ministerios)} ministerios y secretarías de primer nivel.` },
          { n: pct(t.online_pct), label: 'Se pueden iniciar en línea', detail: `${num(tad)} pasan por Trámites a Distancia (TAD); ${pct(t.solo_presencial_pct)} son solo presenciales.` },
          { n: pct(t.arancelados_pct), label: 'Tienen un costo informado', detail: `La mediana de los aranceles en pesos es de $ ${num(a.costos.mediana)}.` },
        ]} />
      </Seccion>

      <Seccion id="organismos" numero="II." eyebrow="Quién atiende"
               titulo={<>Los trámites, <em>por ministerio.</em></>}
               bajada="Área proporcional a la cantidad de trámites. Cada bloque lleva al detalle del organismo.">
        <FadeIn direction="up" distance={8} duration={0.5}>
          <Treemap titulo="Trámites por ministerio" maximo={9}
                   items={a.por_ministerio.map((x) => ({
                     clave: x.slug, etiqueta: x.sigla ?? x.nombre, detalle: x.nombre, valor: x.tramites,
                     href: `/organismos/${x.slug}`,
                   }))} />
        </FadeIn>
      </Seccion>

      <Seccion id="hallazgos" numero="III." eyebrow="Hallazgos" titulo={<>Lo que muestran <em>los datos.</em></>}>
        <div className="ta-hallazgos">
          {hallazgos.map((h, i) => (
            <FadeIn key={h.titulo} direction="up" distance={8} delay={i * 0.05} duration={0.5}>
              <article className="ta-hallazgo">
                <div className="ta-hallazgo-num">{h.n}</div>
                <h3 className="ta-hallazgo-titulo">{h.titulo}</h3>
                <p className="ta-hallazgo-texto">{h.texto}</p>
              </article>
            </FadeIn>
          ))}
        </div>
        <p className="ta-mas"><Link href="/analisis" className="ed-textlink"><span className="ed-textlink-arrow">→</span><span>Ver todos los gráficos</span></Link></p>
      </Seccion>

      <Seccion id="fuentes" numero="IV." eyebrow="De dónde salen los datos"
               titulo={<>Cuatro fuentes, <em>una sola base.</em></>}
               bajada="Todo el proceso es abierto y reproducible: el código y los datos están publicados.">
        <ol className="ta-fuentes">
          {[
            ['Catálogo de TAD', 'El dataset de Trámites a Distancia de Jefatura de Gabinete en datos.gob.ar: nombre, ministerio, arancel y forma de identificarse.'],
            ['Detalle de cada trámite', 'La página pública de cada trámite en TAD: descripción, requisitos y la repartición que lo atiende.'],
            ['Fichas de argentina.gob.ar', 'Para quién es, qué se necesita, cómo se hace y cuánto cuesta, incluidos los trámites presenciales.'],
            ['Inventario propio', 'Los trámites más usados que no pasan por TAD —DNI, pasaporte, ANSES, ARCA, Migraciones— con su norma.'],
          ].map(([titulo, texto], i) => (
            <li key={titulo} className="ta-fuente">
              <span className="ta-fuente-num">{String(i + 1).padStart(2, '0')}</span>
              <h3>{titulo}</h3>
              <p>{texto}</p>
            </li>
          ))}
        </ol>
        <p className="ta-mas">
          <Link href="/metodologia" className="ed-textlink"><span className="ed-textlink-arrow">→</span><span>Metodología y limitaciones</span></Link>
          <Link href="/datos" className="ed-textlink"><span className="ed-textlink-arrow">→</span><span>Descargar los datos</span></Link>
        </p>
      </Seccion>
    </>
  );
}
