// Lectura de los datos exportados. Solo se usa en componentes de servidor y en el build:
// nunca importar desde un componente "use client".
import fs from "node:fs";
import path from "node:path";
import type { Agregados, Meta, Organismo, Tramite } from "./tipos";

const DIR = path.join(process.cwd(), "data");

function leer<T>(archivo: string): T {
  return JSON.parse(fs.readFileSync(path.join(DIR, archivo), "utf-8")) as T;
}

let cacheTramites: Tramite[] | null = null;
let cachePorSlug: Map<string, Tramite> | null = null;

export function tramites(): Tramite[] {
  cacheTramites ??= leer<Tramite[]>("tramites.json");
  return cacheTramites;
}

export function tramite(slug: string): Tramite | undefined {
  cachePorSlug ??= new Map(tramites().map((t) => [t.slug, t]));
  return cachePorSlug.get(slug);
}

/** Trámites que cuentan en los análisis: vigentes y que no son de prueba. */
export function contables(): Tramite[] {
  return tramites().filter((t) => t.estado === "vigente" && !t.prueba);
}

export function organismos(): Organismo[] {
  return leer<Organismo[]>("organismos.json");
}

export function agregados(): Agregados {
  return leer<Agregados>("agregados.json");
}

export function meta(): Meta {
  return leer<Meta>("meta.json");
}
