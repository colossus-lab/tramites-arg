import FadeIn from './FadeIn';

/** Encabezado de sección editorial: eyebrow numerado, título (con <em>) y bajada. */
export default function Seccion({
  id, numero, eyebrow, titulo, bajada, children,
}: {
  id?: string;
  numero?: string;
  eyebrow: string;
  titulo: React.ReactNode;
  bajada?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section className="ed-section" id={id}>
      <div className="ed-container">
        <FadeIn direction="up" distance={8} duration={0.5}>
          <div className="ed-section-head">
            <p className="ed-eyebrow">
              {numero && <span className="ed-eyebrow-num">{numero}</span>}
              <span>{eyebrow}</span>
            </p>
            <h2 className="ed-section-title">{titulo}</h2>
            {bajada && <p className="ed-lead">{bajada}</p>}
          </div>
        </FadeIn>
        {children}
      </div>
    </section>
  );
}

const COLORES_ESCALA = ['var(--ed-cobalt)', 'var(--ed-vermilion)', 'var(--ed-chrome)', 'var(--ed-ink)'];

/** Tabla tipográfica de cifras (ScaleEditorial de OpenArg). El color va por índice porque FadeIn
 *  envuelve cada fila y el :nth-child del CSS original no aplica. */
export function Escala({ filas }: { filas: { n: string; label: string; detail: string }[] }) {
  return (
    <div>
      {filas.map((r, i) => (
        <FadeIn key={r.label} direction="up" distance={8} delay={i * 0.05} duration={0.5}>
          <div className="ed-scale-row">
            <div className="ed-scale-row-num" style={{ color: COLORES_ESCALA[i % COLORES_ESCALA.length] }}>{r.n}</div>
            <div className="ed-scale-row-label">{r.label}</div>
            <div className="ed-scale-row-detail">{r.detail}</div>
          </div>
        </FadeIn>
      ))}
    </div>
  );
}
