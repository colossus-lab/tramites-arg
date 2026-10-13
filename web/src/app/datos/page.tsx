import fs from 'node:fs';
import path from 'node:path';
import type { Metadata } from 'next';
import { meta } from '@/lib/datos';
import { SITIO, fecha } from '@/lib/formato';

export const metadata: Metadata = {
  title: 'Datos abiertos',
  description: 'Descargá la base de trámites del Estado Nacional argentino en CSV y JSON, bajo licencia CC BY 4.0.',
  alternates: { canonical: '/datos' },
};

const ARCHIVOS = [
  { archivo: 'tramites.csv', descripcion: 'Un trámite por fila: organismo, ministerio, categoría, destinatarios, modalidades, plataformas, costo y links a las fuentes.' },
  { archivo: 'requisitos.csv', descripcion: 'Un requisito por fila, con el trámite, el tipo (documento, condición, pago o trámite previo), la sección y la fuente.' },
  { archivo: 'costos.csv', descripcion: 'Un costo por fila: concepto, variante, monto mínimo y máximo, unidad, norma y fuente.' },
  { archivo: 'organismos.csv', descripcion: 'Organismos con su sigla, tipo, de quién dependen, su sucesor y la cantidad de trámites.' },
  { archivo: 'tramites.json', descripcion: 'La base completa en JSON, con canales, requisitos, costos, variantes, fuentes y las descripciones oficiales.' },
];

function tamano(archivo: string): string {
  try {
    const bytes = fs.statSync(path.join(process.cwd(), 'public', 'datos', archivo)).size;
    return bytes > 1e6 ? `${(bytes / 1e6).toLocaleString('es-AR', { maximumFractionDigits: 1 })} MB`
                       : `${Math.round(bytes / 1e3).toLocaleString('es-AR')} KB`;
  } catch {
    return '—';
  }
}

export default function PaginaDatos() {
  const m = meta();
  return (
    <div className="ed-container">
      <header className="ta-cabecera">
        <p className="ed-eyebrow"><span className="ed-eyebrow-num">Descargas</span><span>Datos abiertos</span></p>
        <h1 className="ed-display">Usá los datos.</h1>
        <p className="ed-lead">
          Toda la base está disponible para descargar y reutilizar bajo licencia Creative Commons Atribución 4.0.
          Datos al {fecha(m.fecha_corte)}.
        </p>
      </header>

      <div style={{ padding: '2.5rem 0 1rem' }}>
        <div className="ta-tabla-scroll">
          <table className="ta-tabla">
            <thead><tr><th>Archivo</th><th>Contenido</th><th>Tamaño</th></tr></thead>
            <tbody>
              {ARCHIVOS.map((a) => (
                <tr key={a.archivo}>
                  <td className="ta-num"><a href={`/datos/${a.archivo}`} className="ta-enlace" download>{a.archivo}</a></td>
                  <td>{a.descripcion}</td>
                  <td className="ta-num">{tamano(a.archivo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ta-nota">CSV en UTF-8 separado por comas. Las listas dentro de una celda van separadas por punto y coma.</p>
      </div>

      <div className="ta-prosa" style={{ padding: '1rem 0 4rem' }}>
        <h2>Licencia y atribución</h2>
        <p>
          Los datos se publican bajo <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>. Si los
          usás, citá: <em>Trámites Arg — Colossus Lab ({SITIO.repo})</em>, y las fuentes originales: el dataset de Trámites
          a Distancia de Jefatura de Gabinete en datos.gob.ar, tramitesadistancia.gob.ar y argentina.gob.ar.
        </p>
        <p>
          El código que genera la base está en <a href={SITIO.repo}>GitHub</a> con licencia MIT. Ahí también está el
          esquema completo de la base de datos y el pipeline para regenerarla desde cero.
        </p>
        <p className="ta-aviso">
          Proyecto independiente y no oficial. Los datos pueden tener errores: no los uses como única fuente para
          decisiones legales o administrativas.
        </p>
      </div>
    </div>
  );
}
