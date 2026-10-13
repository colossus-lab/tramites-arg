'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { reemplazarQuery, useQuery } from '@/lib/externo';
import type { FilaIndice } from '@/lib/tipos';
import { DESTINATARIOS, MODALIDADES } from '@/lib/formato';

const POR_PAGINA = 50;

function normalizar(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

interface Filtros {
  q: string;
  categoria: string;
  organismo: string;
  destinatario: string;
  modalidad: string;
  costo: string;
  entreOrganismos: boolean;
  bajas: boolean;
}

const INICIALES: Filtros = {
  q: '', categoria: '', organismo: '', destinatario: '', modalidad: '', costo: '', entreOrganismos: false, bajas: false,
};

function desdeQuery(query: string): Filtros {
  const p = new URLSearchParams(query);
  return {
    q: p.get('q') ?? '', categoria: p.get('categoria') ?? '', organismo: p.get('organismo') ?? '',
    destinatario: p.get('destinatario') ?? '', modalidad: p.get('modalidad') ?? '', costo: p.get('costo') ?? '',
    entreOrganismos: p.get('entre_organismos') === '1', bajas: p.get('bajas') === '1',
  };
}

function aUrl(f: Filtros) {
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.categoria) p.set('categoria', f.categoria);
  if (f.organismo) p.set('organismo', f.organismo);
  if (f.destinatario) p.set('destinatario', f.destinatario);
  if (f.modalidad) p.set('modalidad', f.modalidad);
  if (f.costo) p.set('costo', f.costo);
  if (f.entreOrganismos) p.set('entre_organismos', '1');
  if (f.bajas) p.set('bajas', '1');
  reemplazarQuery(p.toString());
}

function Pastillas({ etiqueta, opciones, valor, onCambio }: {
  etiqueta: string; opciones: [string, string][]; valor: string; onCambio: (v: string) => void;
}) {
  return (
    <div className="ed-dash-pills-row" role="group" aria-label={etiqueta}>
      <span className="ed-dash-pills-label">{etiqueta}</span>
      {opciones.map(([v, nombre]) => (
        <button key={v} type="button" className={`ed-dash-pill${valor === v ? ' is-active' : ''}`}
                aria-pressed={valor === v} onClick={() => onCambio(valor === v ? '' : v)}>
          {nombre}
        </button>
      ))}
    </div>
  );
}

export default function Buscador({ categorias, organismos }: {
  categorias: { codigo: string; nombre: string }[];
  organismos: { slug: string; nombre: string }[];
}) {
  const [indice, setIndice] = useState<FilaIndice[] | null>(null);
  const [error, setError] = useState(false);
  // Los filtros viven en la URL (se pueden compartir); el render los deriva de la query.
  const query = useQuery();
  const f = useMemo(() => desdeQuery(query), [query]);
  const [visibles, setVisibles] = useState(POR_PAGINA);

  useEffect(() => {
    fetch('/indice-busqueda.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setIndice)
      .catch(() => setError(true));
  }, []);

  const cambiar = (parcial: Partial<Filtros>) => {
    setVisibles(POR_PAGINA);
    aUrl({ ...f, ...parcial });
  };

  const nombresCategoria = useMemo(() => Object.fromEntries(categorias.map((c) => [c.codigo, c.nombre])), [categorias]);
  const resultados = useMemo(() => {
    if (!indice) return [];
    const terminos = normalizar(f.q).split(/\s+/).filter(Boolean);
    return indice.filter((t) => {
      if (t.x) return false;
      if (!f.bajas && t.e !== 'vigente') return false;
      if (!f.entreOrganismos && t.d.length === 1 && t.d[0] === 'organismo_publico') return false;
      if (f.categoria && t.c !== f.categoria) return false;
      if (f.organismo && t.os !== f.organismo) return false;
      if (f.destinatario && !t.d.includes(f.destinatario)) return false;
      if (f.modalidad && !t.m.includes(f.modalidad)) return false;
      if (f.costo === 'sin_dato' ? t.g !== null : f.costo && t.g !== f.costo) return false;
      if (terminos.length) {
        const texto = normalizar(`${t.n} ${t.o}`);
        if (!terminos.every((x) => texto.includes(x))) return false;
      }
      return true;
    });
  }, [indice, f]);

  const hayFiltros = JSON.stringify(f) !== JSON.stringify(INICIALES);

  return (
    <div>
      <div className="ed-dash-filters">
        <label className="ed-dash-search">
          <span className="ed-meta" style={{ display: 'block', marginBottom: '0.4rem' }}>Buscar por nombre u organismo</span>
          <input type="search" value={f.q} placeholder="Ej.: pasaporte, apostilla, cooperativa, ANMAT…"
                 onChange={(e) => cambiar({ q: e.target.value })} />
        </label>

        <div className="ed-dash-pills-row">
          <span className="ed-dash-pills-label">Categoría</span>
          <select className="ta-select" value={f.categoria} onChange={(e) => cambiar({ categoria: e.target.value })}
                  aria-label="Categoría">
            <option value="">Todas</option>
            {categorias.map((c) => <option key={c.codigo} value={c.codigo}>{c.nombre}</option>)}
          </select>
          <span className="ed-dash-pills-label">Organismo</span>
          <select className="ta-select" value={f.organismo} onChange={(e) => cambiar({ organismo: e.target.value })}
                  aria-label="Organismo">
            <option value="">Todos</option>
            {organismos.map((o) => <option key={o.slug} value={o.slug}>{o.nombre}</option>)}
          </select>
        </div>

        <Pastillas etiqueta="Para" valor={f.destinatario} onCambio={(v) => cambiar({ destinatario: v })}
                   opciones={['pf_ciudadano', 'empresa', 'profesional', 'organizacion_civil', 'cooperativa_mutual',
                              'pf_extranjero_residente', 'emprendedor'].map((k) => [k, DESTINATARIOS[k]])} />
        <Pastillas etiqueta="Cómo" valor={f.modalidad} onCambio={(v) => cambiar({ modalidad: v })}
                   opciones={['online', 'presencial', 'mixta', 'consular'].map((k) => [k, MODALIDADES[k]])} />
        <Pastillas etiqueta="Costo" valor={f.costo} onCambio={(v) => cambiar({ costo: v })}
                   opciones={[['gratuito', 'Gratuito'], ['arancelado', 'Con costo'], ['sin_dato', 'Sin dato']]} />

        <div className="ed-dash-pills-row">
          <span className="ed-dash-pills-label">Incluir</span>
          <button type="button" className={`ed-dash-pill${f.entreOrganismos ? ' is-active' : ''}`} aria-pressed={f.entreOrganismos}
                  onClick={() => cambiar({ entreOrganismos: !f.entreOrganismos })}>
            Trámites entre organismos del Estado
          </button>
          <button type="button" className={`ed-dash-pill${f.bajas ? ' is-active' : ''}`} aria-pressed={f.bajas}
                  onClick={() => cambiar({ bajas: !f.bajas })}>
            Dados de baja
          </button>
          {hayFiltros && (
            <button type="button" className="ed-dash-clear" onClick={() => cambiar(INICIALES)}>Limpiar filtros</button>
          )}
        </div>
      </div>

      <p className="ed-dash-count" aria-live="polite">
        {error ? 'No se pudo cargar el índice de trámites.' : indice === null ? 'Cargando…' : (
          <><strong>{resultados.length.toLocaleString('es-AR')}</strong> trámites</>
        )}
      </p>

      <ul className="ta-resultados">
        {resultados.slice(0, visibles).map((t) => (
          <li key={t.s} className="ta-resultado">
            <Link href={`/tramites/${t.s}`}>
              <span className="ta-resultado-nombre">{t.n}</span>
              <span className="ta-resultado-org">{t.o}</span>
              <span className="ta-etiquetas">
                {t.c && <span className="ta-etiqueta">{nombresCategoria[t.c] ?? t.c}</span>}
                {t.m.map((m) => <span key={m} className="ta-etiqueta ta-etiqueta--celeste">{MODALIDADES[m] ?? m}</span>)}
                {t.g === 'arancelado' && <span className="ta-etiqueta ta-etiqueta--acento">Con costo</span>}
                {t.g === 'gratuito' && <span className="ta-etiqueta">Gratuito</span>}
                {t.e !== 'vigente' && <span className="ta-etiqueta ta-etiqueta--baja">Dado de baja</span>}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {indice && resultados.length === 0 && (
        <p className="ed-dash-empty">No hay trámites con esos filtros. Probá con otra palabra o limpiá los filtros.</p>
      )}
      {resultados.length > visibles && (
        <button type="button" className="ta-boton" onClick={() => setVisibles((v) => v + POR_PAGINA)}>
          Ver {Math.min(POR_PAGINA, resultados.length - visibles)} más
        </button>
      )}
    </div>
  );
}
