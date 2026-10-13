import type { Metadata } from 'next';
import Buscador from '@/components/Buscador';
import { agregados, organismos } from '@/lib/datos';
import { num } from '@/lib/formato';

export const metadata: Metadata = {
  title: 'Buscar trámites',
  description: 'Buscá entre los trámites del Estado Nacional argentino por nombre, organismo, categoría, destinatario, modalidad y costo.',
  alternates: { canonical: '/tramites' },
};

export default function PaginaTramites() {
  const a = agregados();
  const categorias = a.por_categoria
    .filter((c) => c.codigo !== 'sin_categoria')
    .map((c) => ({ codigo: c.codigo, nombre: c.nombre }))
    .sort((x, y) => x.nombre.localeCompare(y.nombre, 'es'));
  const lista = organismos()
    .filter((o) => o.tramites > 0)
    .map((o) => ({ slug: o.slug, nombre: o.sigla ? `${o.nombre} (${o.sigla})` : o.nombre }))
    .sort((x, y) => x.nombre.localeCompare(y.nombre, 'es'));

  return (
    <div className="ed-container">
      <header className="ta-cabecera">
        <p className="ed-eyebrow"><span className="ed-eyebrow-num">Buscador</span><span>Trámites</span></p>
        <h1 className="ed-display">Encontrá un trámite.</h1>
        <p className="ed-lead">
          {num(a.totales.tramites)} trámites vigentes de {num(a.totales.organismos)} organismos. Cada ficha enlaza a la
          fuente oficial, que es la que vale ante cualquier diferencia.
        </p>
      </header>
      <div style={{ padding: '2rem 0 4rem' }}>
        <Buscador categorias={categorias} organismos={lista} />
      </div>
    </div>
  );
}
