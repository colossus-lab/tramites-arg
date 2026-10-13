// Jerarquía de organismos a partir de organismos.json (solo servidor).
import { contables, organismos } from './datos';
import type { Organismo, Tramite } from './tipos';

export interface Nodo extends Organismo {
  hijos: Nodo[];
  total: number; // trámites propios + de todas las dependencias
}

let cache: { porSlug: Map<string, Nodo>; raices: Nodo[] } | null = null;

export function jerarquia() {
  if (cache) return cache;
  const porSlug = new Map<string, Nodo>(organismos().map((o) => [o.slug, { ...o, hijos: [], total: 0 }]));
  const raices: Nodo[] = [];
  for (const n of porSlug.values()) {
    const padre = n.padre ? porSlug.get(n.padre) : undefined;
    if (padre) padre.hijos.push(n);
    else raices.push(n);
  }
  const sumar = (n: Nodo): number => (n.total = n.tramites + n.hijos.reduce((s, h) => s + sumar(h), 0));
  raices.forEach(sumar);
  const ordenar = (lista: Nodo[]) => {
    lista.sort((a, b) => b.total - a.total || a.nombre.localeCompare(b.nombre, 'es'));
    lista.forEach((n) => ordenar(n.hijos));
  };
  ordenar(raices);
  cache = { porSlug, raices };
  return cache;
}

export function descendientes(n: Nodo): Nodo[] {
  return n.hijos.flatMap((h) => [h, ...descendientes(h)]);
}

/** Trámites contables del organismo y de sus dependencias. */
export function tramitesDe(n: Nodo): Tramite[] {
  const slugs = new Set([n.slug, ...descendientes(n).map((d) => d.slug)]);
  return contables().filter((t) => slugs.has(t.organismo.slug));
}
