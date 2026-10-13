'use client';

// Adaptado de ThemeToggleEditorial de OpenArg (github.com/colossus-lab/openarg_frontend, MIT).
// El tema inicial lo aplica el script de layout.tsx antes de pintar; acá solo se lee y se cambia.

import { useTema } from '@/lib/externo';

export const STORAGE_KEY = 'tramitesarg-theme';

export default function ThemeToggle() {
  const tema = useTema();

  const cambiar = () => {
    const siguiente = tema === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', siguiente);
    try {
      window.localStorage.setItem(STORAGE_KEY, siguiente);
    } catch {
      /* sin almacenamiento disponible */
    }
  };

  // En el servidor no se conoce el tema: se reserva el espacio para evitar saltos.
  if (!tema) return <span className="ed-theme-toggle" aria-hidden="true" />;

  return (
    <button type="button" className="ed-theme-toggle" onClick={cambiar}
            aria-label={`Cambiar a modo ${tema === 'dark' ? 'claro' : 'oscuro'}`}
            title={tema === 'dark' ? 'Modo claro' : 'Modo oscuro'}>
      {tema === 'dark' ? (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
          <path d="M8 1.5v1.5M8 13v1.5M14.5 8H13M3 8H1.5M12.6 3.4l-1.05 1.05M4.45 11.55L3.4 12.6M12.6 12.6l-1.05-1.05M4.45 4.45L3.4 3.4"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M13.5 9.4A5.5 5.5 0 1 1 6.6 2.5a6 6 0 0 0 6.9 6.9z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}
