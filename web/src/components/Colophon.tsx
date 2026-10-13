import Link from 'next/link';
import { SITIO } from '@/lib/formato';

export default function Colophon({ fechaCorte }: { fechaCorte: string }) {
  return (
    <footer className="ed-colophon">
      <div className="ed-container">
        <div className="ed-colophon-grid">
          <div className="ed-colophon-brand">
            <span className="ed-colophon-brand-name">Trámites Arg</span>
            <span className="ed-colophon-brand-sub">por Colossus Lab</span>
            <p className="ta-colophon-desc">
              Proyecto independiente y <strong>no oficial</strong>. No está afiliado al Gobierno de la
              República Argentina. Ante cualquier duda, consultá la fuente oficial de cada trámite.
            </p>
          </div>

          <div className="ed-colophon-col">
            <span className="ed-colophon-col-title">Explorar</span>
            <Link href="/tramites">Trámites</Link>
            <Link href="/organismos">Organismos</Link>
            <Link href="/analisis">Análisis</Link>
            <Link href="/metodologia">Metodología</Link>
            <Link href="/datos">Datos abiertos</Link>
          </div>

          <div className="ed-colophon-col">
            <span className="ed-colophon-col-title">Colossus Lab</span>
            <a href="https://colossuslab.org" target="_blank" rel="noopener noreferrer">Sitio del laboratorio</a>
            <a href={SITIO.repo} target="_blank" rel="noopener noreferrer">Código en GitHub</a>
            <a href={`${SITIO.repo}/issues`} target="_blank" rel="noopener noreferrer">Reportar un error</a>
            <a href="mailto:devops@colossuslab.org">Contacto</a>
          </div>

          <div className="ed-colophon-col">
            <span className="ed-colophon-col-title">Fuentes</span>
            <a href="https://tramitesadistancia.gob.ar" target="_blank" rel="noopener noreferrer">Trámites a Distancia</a>
            <a href="https://datos.gob.ar" target="_blank" rel="noopener noreferrer">Datos Argentina</a>
            <a href="https://www.argentina.gob.ar" target="_blank" rel="noopener noreferrer">argentina.gob.ar</a>
          </div>
        </div>

        <div className="ed-colophon-bottom">
          <span>
            Código MIT · Datos CC BY 4.0 · Corte de datos: <em>{fechaCorte}</em>
          </span>
          <span>Compuesto en Familjen Grotesk e Inter. Datos públicos verificables.</span>
        </div>
      </div>
    </footer>
  );
}
