import type { MetadataRoute } from 'next';
import { meta, tramites } from '@/lib/datos';
import { jerarquia } from '@/lib/organismos';
import { SITIO } from '@/lib/formato';

export default function sitemap(): MetadataRoute.Sitemap {
  const fecha = new Date(meta().fecha_corte);
  const fijas = ['', '/tramites', '/organismos', '/analisis', '/metodologia', '/datos'].map((ruta) => ({
    url: `${SITIO.url}${ruta}`, lastModified: fecha, changeFrequency: 'monthly' as const, priority: ruta === '' ? 1 : 0.8,
  }));
  const organismos = [...jerarquia().porSlug.values()].filter((n) => n.total > 0 || n.sucesor).map((n) => ({
    url: `${SITIO.url}/organismos/${n.slug}`, lastModified: fecha, changeFrequency: 'monthly' as const, priority: 0.6,
  }));
  const fichas = tramites().map((t) => ({
    url: `${SITIO.url}/tramites/${t.slug}`, lastModified: fecha, changeFrequency: 'monthly' as const, priority: 0.5,
  }));
  return [...fijas, ...organismos, ...fichas];
}
