'use client';

// Gráficos de barras con el estilo de los charts de OpenArg: colores tomados de las variables
// CSS del tema (se vuelven a leer cuando cambia data-theme) y números en formato es-AR.

import { useMemo } from 'react';
import { useTema as useModo } from '@/lib/externo';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

interface Tema {
  grid: string;
  axis: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  serie: string[];
}

const SERIE_POR_DEFECTO = ['#74ACDF', '#F6B40E', '#34D399', '#F59E0B', '#A78BFA', '#F87171', '#60A5FA', '#FBBF24'];

function leerTema(): Tema {
  const el = document.querySelector('.ed-page') ?? document.documentElement;
  const css = getComputedStyle(el);
  const v = (nombre: string, defecto: string) => css.getPropertyValue(nombre).trim() || defecto;
  return {
    grid: v('--chart-grid', 'rgba(116,172,223,0.10)'),
    axis: v('--chart-axis', '#6B7280'),
    tooltipBg: v('--chart-tooltip-bg', '#1A1F35'),
    tooltipBorder: v('--chart-tooltip-border', 'rgba(116,172,223,0.2)'),
    tooltipText: v('--chart-tooltip-text', '#F0F4FC'),
    serie: [v('--ed-cobalt', SERIE_POR_DEFECTO[0]), v('--ed-vermilion', SERIE_POR_DEFECTO[1]), ...SERIE_POR_DEFECTO.slice(2)],
  };
}

/** Colores del tema actual; se recalculan cuando cambia data-theme. Null en el servidor. */
function useTema(): Tema | null {
  const modo = useModo();
  return useMemo(() => (modo ? leerTema() : null), [modo]);
}

const fmt = (n: number) => n.toLocaleString('es-AR');

export interface Dato {
  etiqueta: string;
  valor: number;
}

export function Barras({
  datos, horizontal = true, alto, unidad = 'trámites', colorear = false, etiquetaAncho = 190,
}: {
  datos: Dato[];
  horizontal?: boolean;
  alto?: number;
  unidad?: string;
  colorear?: boolean;
  etiquetaAncho?: number;
}) {
  const tema = useTema();
  const altura = alto ?? (horizontal ? Math.max(180, datos.length * 30 + 40) : 300);
  if (!tema) return <div className="ta-chart-placeholder" style={{ height: altura }} aria-hidden="true" />;
  const tooltip = (
    <Tooltip
      cursor={{ fill: tema.grid }}
      formatter={(v) => [`${fmt(Number(v))} ${unidad}`, '']}
      separator=""
      contentStyle={{ background: tema.tooltipBg, border: `1px solid ${tema.tooltipBorder}`, borderRadius: 8,
                      color: tema.tooltipText, fontSize: 12 }}
      labelStyle={{ color: tema.tooltipText, fontWeight: 600 }}
      itemStyle={{ color: tema.tooltipText }}
    />
  );
  return (
    <div className="ta-chart" role="img" aria-label={datos.map((d) => `${d.etiqueta}: ${fmt(d.valor)}`).join('; ')}>
      <ResponsiveContainer width="100%" height={altura}>
        {horizontal ? (
          <BarChart data={datos} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={tema.grid} horizontal={false} />
            <XAxis type="number" tick={{ fill: tema.axis, fontSize: 12 }} tickFormatter={fmt} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="etiqueta" width={etiquetaAncho} tick={{ fill: tema.axis, fontSize: 12 }}
                   axisLine={false} tickLine={false} interval={0} />
            {tooltip}
            <Bar dataKey="valor" radius={[0, 4, 4, 0]} fill={tema.serie[0]} isAnimationActive={false}>
              {colorear && datos.map((d, i) => <Cell key={d.etiqueta} fill={tema.serie[i % tema.serie.length]} />)}
            </Bar>
          </BarChart>
        ) : (
          <BarChart data={datos} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={tema.grid} vertical={false} />
            <XAxis dataKey="etiqueta" tick={{ fill: tema.axis, fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: tema.axis, fontSize: 12 }} tickFormatter={fmt} axisLine={false} tickLine={false} width={48} />
            {tooltip}
            <Bar dataKey="valor" radius={[4, 4, 0, 0]} fill={tema.serie[0]} isAnimationActive={false}>
              {colorear && datos.map((d, i) => <Cell key={d.etiqueta} fill={tema.serie[i % tema.serie.length]} />)}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
