import type { Metadata } from 'next';
import Link from 'next/link';
import { agregados, meta } from '@/lib/datos';
import { SITIO, fecha, num } from '@/lib/formato';

export const metadata: Metadata = {
  title: 'Metodología',
  description: 'De dónde salen los datos de Trámites Arg, cómo se cuentan los trámites, cómo se clasifican y cuáles son sus limitaciones.',
  alternates: { canonical: '/metodologia' },
};

export default function PaginaMetodologia() {
  const a = agregados();
  const m = meta();
  const t = a.totales;
  return (
    <div className="ed-container">
      <header className="ta-cabecera">
        <p className="ed-eyebrow"><span className="ed-eyebrow-num">Metodología</span><span>Cómo se armó</span></p>
        <h1 className="ed-display">De dónde salen los datos.</h1>
        <p className="ed-lead">
          Trámites Arg reúne en una sola base los trámites del Estado Nacional que hoy están repartidos entre
          plataformas y sitios distintos. Todo el proceso es automático, abierto y reproducible.
        </p>
      </header>

      <div className="ta-prosa" style={{ padding: '2.5rem 0 4rem' }}>
        <p className="ta-aviso">
          <strong>Proyecto independiente y no oficial.</strong> Trámites Arg no está afiliado al Gobierno de la
          República Argentina ni a ninguno de sus organismos. Los datos pueden contener errores de extracción o estar
          desactualizados: ante cualquier diferencia, vale lo que diga la fuente oficial enlazada en cada trámite.
        </p>

        <h2>Qué cuenta como un trámite</h2>
        <p>
          Un trámite es una solicitud ante un organismo que tiene un resultado propio: inscribirse en un registro,
          renovar una licencia o pedir un certificado son trámites distintos aunque se parezcan. En cambio, cuando lo
          único que cambia es el tipo de persona (humana o jurídica), el plazo o el precio, se cuenta un solo trámite
          con variantes. Con esta regla, la base tiene <strong>{num(t.tramites)} trámites vigentes</strong> y {num(t.variantes)} variantes.
        </p>
        <p>No se cuentan: los trámites dados de baja ({num(t.bajas)}), los que se fusionaron en otro como variante y {num(t.prueba)} trámites del catálogo oficial que parecen ser pruebas de la plataforma.</p>
        <p>
          Tampoco se cuentan {num(t.consultas)} <strong>servicios de consulta</strong>: páginas que permiten ver un dato
          (el padrón electoral, el calendario de pagos de ANSES, el estado de un expediente) sin pedirle nada al
          organismo. Aparecen en el buscador, marcados, pero quedan fuera de los totales y los gráficos. Las consultas
          formales que el organismo responde con un acto propio, como la clasificación de un producto, sí son trámites.
        </p>

        <h2>Fuentes</h2>
        <ol>
          <li>
            <strong>Catálogo de Trámites a Distancia (TAD).</strong> El dataset «Plataforma de Trámites a Distancia» de
            Jefatura de Gabinete, publicado en <a href="https://datos.gob.ar">datos.gob.ar</a>: nombre, ministerio,
            fecha de publicación, si es arancelado y con qué claves se puede ingresar.
          </li>
          <li>
            <strong>Detalle de cada trámite en TAD.</strong> La página pública de cada trámite en
            tramitesadistancia.gob.ar: descripción, requisitos y la repartición que lo inicia, que permite saber qué
            organismo lo atiende y no solo el ministerio.
          </li>
          <li>
            <strong>Fichas de argentina.gob.ar.</strong> Las fichas «¿A quién está dirigido?», «¿Qué necesito?»,
            «¿Cómo hago?» y «¿Cuál es el costo?», que suman trámites presenciales y de otras plataformas. Se leen
            respetando el <code>robots.txt</code> del sitio, con diez segundos entre pedidos.
          </li>
          <li>
            <strong>Relevamiento propio.</strong> Un inventario curado de los trámites más usados que no pasan por TAD
            (DNI, pasaporte, jubilaciones, AUH, clave fiscal, monotributo, radicaciones, transferencias de autos), con
            sus variantes, costos y la norma que los fija.
          </li>
        </ol>
        <p>
          Cuando dos fuentes hablan del mismo trámite se unen en una sola ficha: por el número de TAD cuando la ficha de
          argentina.gob.ar lo enlaza, o por similitud del nombre dentro del mismo ministerio. Los casos dudosos se
          revisan a mano y la decisión queda versionada en el repositorio. Las fichas que no se vinculan con ningún
          trámite existente se suman como trámites nuevos.
        </p>

        <h2>Organismos</h2>
        <p>
          El catálogo de TAD solo informa el ministerio. El organismo que atiende cada trámite se deduce de la repartición
          que lo inicia en el sistema de expedientes del Estado y, para las fichas, de la ruta de navegación de
          argentina.gob.ar. Los organismos disueltos o renombrados entre 2024 y 2026 (AFIP → ARCA, ANMaC → RENAR,
          ANDIS → Secretaría Nacional de Discapacidad) se modelan como antecesores, y sus trámites se muestran en el sucesor.
        </p>

        <h2>Clasificación</h2>
        <p>
          La categoría y los destinatarios se asignan con reglas explícitas y auditables, publicadas en el código. Cada
          asignación guarda qué regla la produjo:
        </p>
        <ul>
          <li><strong>Manual:</strong> los trámites del relevamiento propio.</li>
          <li><strong>Confianza alta:</strong> por el organismo (SENASA → agro, ANMAT → salud), por hablar de importación o exportación, o por palabras clave del nombre.</li>
          <li><strong>Confianza baja:</strong> por las etiquetas temáticas de TAD o, en último caso, por el ministerio. La ficha de cada trámite lo indica.</li>
        </ul>
        <p>Si ninguna regla aplica, el trámite queda sin categoría en lugar de forzarlo en una equivocada.</p>
        <p>
          Los canales (en línea, presencial, por correo) salen del catálogo de TAD, de los botones de inicio de cada
          ficha y, si no los hay, del texto de «¿Cómo hago?». También es una lectura heurística del texto.
        </p>

        <h2>Requisitos y costos</h2>
        <p>
          Los requisitos se extraen de las secciones «Requisitos», «Documentación» o «¿Qué necesito?» de cada
          descripción, y los costos de los montos que aparecen en contexto de arancel o tasa. Como cada organismo redacta
          sus textos a su manera, la extracción es heurística: puede faltar algún requisito o colarse una aclaración.
          Cada dato muestra de qué fuente salió.
        </p>
        <p>
          Una advertencia sobre los costos: el catálogo de TAD marca como «no arancelados» a {num(a.costos.subestimados_csv_tad)} trámites
          cuya descripción o ficha informa un monto a pagar. Por eso la base combina todas las fuentes y, cuando no
          coinciden, muestra las diferencias en lugar de elegir una.
        </p>

        <h2>Limitaciones</h2>
        <ul>
          <li>Muchos trámites de TAD no detallan sus requisitos en la descripción: los documentos se piden dentro del formulario, al que solo se accede con sesión iniciada.</li>
          <li>Faltan los trámites de plataformas propias que no tienen ficha pública (por ejemplo, buena parte de los servicios con clave fiscal de ARCA).</li>
          <li>Los montos cambian varias veces por año. Cada costo indica su fuente y, cuando se conoce, la norma y la fecha.</li>
          <li>La base cubre solo el Estado Nacional. Provincias y municipios quedan para próximas etapas.</li>
        </ul>

        <h2>Actualización</h2>
        <p>
          Datos al <strong>{fecha(m.fecha_corte)}</strong>. Trámite publicado más reciente en TAD: {fecha(m.max_fecha_publicacion_tad)}.
          La actualización se corre manualmente con el pipeline del repositorio; cada corrida registra altas, cambios y
          bajas de cada fuente.
        </p>

        <h2>Código, datos y correcciones</h2>
        <p>
          El código es abierto (licencia MIT) y está en <a href={SITIO.repo}>GitHub</a>. Los datos se pueden descargar
          desde <Link href="/datos">Datos abiertos</Link> bajo licencia CC BY 4.0. Si encontrás un error, abrí un
          {' '}<a href={`${SITIO.repo}/issues`}>issue</a> con el link a la fuente oficial que lo respalda.
        </p>
      </div>
    </div>
  );
}
