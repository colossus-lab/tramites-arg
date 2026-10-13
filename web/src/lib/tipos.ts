// Tipos de los archivos que genera scripts/exportar_web.py.

export interface OrganismoRef {
  slug: string;
  sigla: string | null;
  nombre: string;
  ministerio: { slug: string; sigla: string | null; nombre: string } | null;
}

export interface Canal {
  modalidad: "online" | "presencial" | "mixta" | "telefonica" | "consular" | "correo";
  plataforma: string | null;
  plataforma_nombre: string | null;
  url: string | null;
  requiere_turno: boolean | null;
  detalle: string | null;
  autenticacion: string[];
}

export type FuentePublica = "tad" | "ficha" | "inventario" | "manual";

export interface Requisito {
  descripcion: string;
  tipo: "documento" | "condicion" | "pago_previo" | "tramite_previo";
  seccion: string | null;
  obligatorio: boolean;
  fuente: FuentePublica;
  previo: string | null;
}

export interface Costo {
  concepto: string;
  gratuito: boolean;
  monto_min: number | null;
  monto_max: number | null;
  unidad: string;
  norma: string | null;
  detalle: string | null;
  variante: string | null;
  vigente_desde: string | null;
  fuente: FuentePublica;
}

export interface Fuente {
  tipo: "tad" | "ficha" | "inventario";
  id: string;
  activo: boolean;
  url: string | null;
  capturado: string;
  actualizado?: string | null;
}

export interface Tramite {
  slug: string;
  nombre: string;
  descripcion: string | null;
  estado: "vigente" | "baja" | "migrado" | "suspendido" | "fusionado";
  prueba: boolean;
  organismo: OrganismoRef;
  categoria: { codigo: string; nombre: string } | null;
  categoria_confianza: "manual" | "alta" | "baja" | null;
  destinatarios: string[];
  variantes: { nombre: string; id_tad: string | null }[];
  canales: Canal[];
  requisitos: Requisito[];
  costos: Costo[];
  fuentes: Fuente[];
  descripciones: { tad?: string | null; ficha?: Record<string, string | null> };
  reemplazado_por: string | null;
  fecha_publicacion_tad: string | null;
  fecha_verificacion: string | null;
  norma: string | null;
}

export interface Organismo {
  slug: string;
  sigla: string | null;
  nombre: string;
  tipo: string | null;
  padre: string | null;
  sucesor: string | null;
  vigente_hasta: string | null;
  norma_creacion: string | null;
  norma_disolucion: string | null;
  tramites: number;
}

/** Fila del índice de búsqueda (claves cortas para que pese poco). */
export interface FilaIndice {
  s: string; // slug
  n: string; // nombre
  o: string; // organismo (sigla o nombre)
  os: string; // slug del organismo
  c: string | null; // categoría
  d: string[]; // destinatarios
  m: string[]; // modalidades
  p: string[]; // plataformas
  g: "gratuito" | "arancelado" | null; // costo
  e: Tramite["estado"];
  x: boolean; // trámite de prueba
}

export interface Agregados {
  totales: {
    tramites: number;
    organismos: number;
    ministerios: number;
    online_pct: number;
    presencial_pct: number;
    arancelados_pct: number;
    gratuitos_pct: number;
    costo_sin_dato_pct: number;
    con_requisitos_pct: number;
    con_categoria_pct: number;
    con_destinatario_pct: number;
    para_ciudadanos_y_empresas: number;
    variantes: number;
    bajas: number;
    prueba: number;
    por_fuente: Record<string, number>;
  };
  por_categoria: { codigo: string; nombre: string; tramites: number }[];
  por_ministerio: { slug: string; sigla: string | null; nombre: string; tramites: number }[];
  por_organismo: { slug: string; sigla: string | null; nombre: string; tramites: number }[];
  por_plataforma: { plataforma: string; tramites: number }[];
  autenticacion: { metodo: string; tramites: number }[];
  por_destinatario: { tipo: string; tramites: number }[];
  por_anio_publicacion_tad: { anio: string; tramites: number }[];
  costos: {
    gratuitos: number;
    arancelados: number;
    sin_dato: number;
    subestimados_csv_tad: number;
    distribucion: { tramo: string; tramites: number }[];
    mediana: number | null;
    discrepancias: { slug: string; nombre: string; csv: number; otra_fuente: number; fuente: string }[];
  };
  requisitos_top: { documento: string; tramites: number }[];
  cambios_institucionales: {
    anterior: string;
    anterior_sigla: string | null;
    sucesor: string;
    sucesor_sigla: string | null;
    sucesor_slug: string;
    fecha: string | null;
    norma: string | null;
    tramites: number;
  }[];
}

export interface Meta {
  fecha_corte: string;
  max_fecha_publicacion_tad: string | null;
  ultimas_corridas: Record<string, string>;
}
