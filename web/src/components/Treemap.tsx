import Link from 'next/link';
import { num } from '@/lib/formato';

// Treemap con el estilo de GeoBlocksMap de OpenArg, pero calculado a partir de los datos
// (algoritmo "squarified" de Bruls, Huizing y van Wijk).

export interface ItemTreemap {
  clave: string;
  etiqueta: string;
  detalle?: string;
  valor: number;
  href?: string;
}

interface Rect { x: number; y: number; w: number; h: number }

const COLORES = [
  'var(--ed-cobalt)', 'var(--ed-vermilion)', 'var(--ed-celeste)', 'var(--ed-chrome)',
  'rgba(116, 172, 223, 0.7)', 'rgba(246, 180, 14, 0.7)', 'var(--ed-ink)', 'var(--ed-paper-3)',
];

function peor(fila: number[], lado: number): number {
  const suma = fila.reduce((a, b) => a + b, 0);
  const max = Math.max(...fila);
  const min = Math.min(...fila);
  return Math.max((lado * lado * max) / (suma * suma), (suma * suma) / (lado * lado * min));
}

function squarify(valores: number[], r: Rect): Rect[] {
  const salida: Rect[] = [];
  let resto = [...valores];
  let caja = { ...r };
  while (resto.length) {
    const lado = Math.min(caja.w, caja.h);
    const fila: number[] = [resto[0]];
    let i = 1;
    while (i < resto.length && peor([...fila, resto[i]], lado) <= peor(fila, lado)) {
      fila.push(resto[i]);
      i++;
    }
    const suma = fila.reduce((a, b) => a + b, 0);
    if (caja.w >= caja.h) {
      const ancho = suma / caja.h;
      let y = caja.y;
      for (const v of fila) {
        const alto = v / ancho;
        salida.push({ x: caja.x, y, w: ancho, h: alto });
        y += alto;
      }
      caja = { x: caja.x + ancho, y: caja.y, w: caja.w - ancho, h: caja.h };
    } else {
      const alto = suma / caja.w;
      let x = caja.x;
      for (const v of fila) {
        const ancho = v / alto;
        salida.push({ x, y: caja.y, w: ancho, h: alto });
        x += ancho;
      }
      caja = { x: caja.x, y: caja.y + alto, w: caja.w, h: caja.h - alto };
    }
    resto = resto.slice(i);
  }
  return salida;
}

export default function Treemap({ items, titulo, maximo = 10 }: { items: ItemTreemap[]; titulo: string; maximo?: number }) {
  const ordenados = [...items].sort((a, b) => b.valor - a.valor);
  const principales = ordenados.slice(0, maximo);
  const otros = ordenados.slice(maximo);
  if (otros.length) {
    principales.push({
      clave: '_otros',
      etiqueta: `Otros (${otros.length})`,
      valor: otros.reduce((a, b) => a + b.valor, 0),
    });
  }
  const total = principales.reduce((a, b) => a + b.valor, 0);
  // El lienzo de .ed-geomap-canvas es 16:6, o sea 100 × 37,5: las áreas se escalan a esa superficie.
  const W = 100, H = 37.5;
  const rects = squarify(principales.map((p) => (p.valor / total) * W * H), { x: 0, y: 0, w: W, h: H });

  return (
    <div className="ed-geomap">
      <div className="ed-geomap-canvas" role="img" aria-label={titulo}>
        {principales.map((p, i) => {
          const r = rects[i];
          const area = r.w * r.h;
          const tamano = Math.max(1, Math.min(3.2, area / 300 + 1));
          const color = p.clave === '_otros' ? 'var(--ed-paper-3)' : COLORES[i % COLORES.length];
          const claro = color === 'var(--ed-paper-3)';
          const contenido = (
            <>
              <span className="ed-geomap-region-label">{p.etiqueta}</span>
              {area > 60 && <span className="ed-geomap-region-num" style={{ fontSize: `${tamano}rem` }}>{num(p.valor)}</span>}
              {area > 110 && <span className="ed-geomap-region-share">{Math.round((p.valor / total) * 100)}%</span>}
              {area > 350 && p.detalle && <span className="ed-geomap-region-list">{p.detalle}</span>}
            </>
          );
          const estilo = {
            left: `${r.x}%`, top: `${(r.y / H) * 100}%`, width: `${r.w}%`, height: `${(r.h / H) * 100}%`,
            background: color, color: claro ? 'var(--ed-ink)' : '#06090F',
            borderColor: claro ? 'rgba(116, 172, 223, 0.35)' : 'rgba(6, 9, 15, 0.15)',
          };
          return p.href ? (
            <Link key={p.clave} href={p.href} className="ed-geomap-region ta-treemap-link" style={estilo}
                  title={`${p.etiqueta}: ${num(p.valor)} trámites`}>
              {contenido}
            </Link>
          ) : (
            <div key={p.clave} className="ed-geomap-region" style={estilo} title={`${p.etiqueta}: ${num(p.valor)}`}>
              {contenido}
            </div>
          );
        })}
      </div>

      <aside className="ed-geomap-aside">
        <p className="ed-meta">{titulo}</p>
        <ul className="ed-geomap-legend">
          {principales.map((p, i) => (
            <li key={p.clave}>
              <span className="ed-geomap-legend-swatch"
                    style={{ background: p.clave === '_otros' ? 'var(--ed-paper-3)' : COLORES[i % COLORES.length] }} />
              <span>{p.etiqueta}</span>
              <span className="ed-geomap-legend-num">{num(p.valor)}</span>
            </li>
          ))}
        </ul>
        <p className="ed-meta-mono">Total: {num(total)} trámites.</p>
      </aside>
    </div>
  );
}
