// Formatos y etiquetas compartidos (servidor y cliente).

export const SITIO = {
  nombre: "Trámites Arg",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://tramites-arg.vercel.app",
  repo: "https://github.com/colossus-lab/tramites-arg",
};

export function num(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("es-AR");
}

export function pct(n: number): string {
  return `${n.toLocaleString("es-AR", { maximumFractionDigits: 1 })} %`;
}

export function fecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

const SIMBOLO: Record<string, string> = { ARS: "$", USD: "USD", EUR: "EUR" };

export function monto(valor: number | null, unidad: string): string {
  if (valor == null) return "—";
  const n = valor.toLocaleString("es-AR", { maximumFractionDigits: 2 });
  if (unidad === "UMSM") return `${n} UMSM`;
  return `${SIMBOLO[unidad] ?? unidad} ${n}`;
}

export const DESTINATARIOS: Record<string, string> = {
  pf_ciudadano: "Personas",
  pf_extranjero_residente: "Extranjeros residentes",
  pf_no_residente: "No residentes",
  empresa: "Empresas",
  emprendedor: "Emprendedores",
  organizacion_civil: "Organizaciones civiles",
  cooperativa_mutual: "Cooperativas y mutuales",
  organismo_publico: "Organismos públicos",
  profesional: "Profesionales",
};

export const MODALIDADES: Record<string, string> = {
  online: "En línea",
  presencial: "Presencial",
  mixta: "Mixta",
  telefonica: "Telefónica",
  consular: "Consular",
  correo: "Por correo",
};

export const AUTENTICACION: Record<string, string> = {
  clave_fiscal: "Clave fiscal (ARCA)",
  mi_argentina: "Mi Argentina",
  mi_argentina_validado: "Mi Argentina (validada)",
  css_anses: "Clave de la Seguridad Social (ANSES)",
  dni_tramite: "DNI y n.º de trámite",
  nic_no_residente: "NIC para no residentes",
  firma_digital: "Firma digital",
  sin_autenticacion: "Sin clave",
  otro: "Otro",
};

export const FUENTES: Record<string, string> = {
  tad: "Trámites a Distancia",
  ficha: "argentina.gob.ar",
  inventario: "Relevamiento propio",
  manual: "Carga manual",
};

export const TIPO_REQUISITO: Record<string, string> = {
  documento: "Documento",
  condicion: "Condición",
  pago_previo: "Pago previo",
  tramite_previo: "Trámite previo",
};

export const ESTADOS: Record<string, string> = {
  vigente: "Vigente",
  baja: "Dado de baja",
  migrado: "Migrado",
  suspendido: "Suspendido",
  fusionado: "Fusionado",
};
