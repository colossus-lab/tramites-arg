'use client';

// Estado que vive fuera de React (tema en <html data-theme> y la query de la URL), leído con
// useSyncExternalStore para no sincronizarlo a mano dentro de efectos.

import { useSyncExternalStore } from 'react';

export type Tema = 'light' | 'dark';

function suscribirTema(aviso: () => void) {
  const obs = new MutationObserver(aviso);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  return () => obs.disconnect();
}

/** Tema actual, o null durante el render del servidor. */
export function useTema(): Tema | null {
  return useSyncExternalStore(
    suscribirTema,
    () => (document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'),
    () => null,
  );
}

const EVENTO_URL = 'tramitesarg:url';

function suscribirUrl(aviso: () => void) {
  window.addEventListener('popstate', aviso);
  window.addEventListener(EVENTO_URL, aviso);
  return () => {
    window.removeEventListener('popstate', aviso);
    window.removeEventListener(EVENTO_URL, aviso);
  };
}

/** Query string actual ('' en el servidor). */
export function useQuery(): string {
  return useSyncExternalStore(suscribirUrl, () => window.location.search, () => '');
}

/** Reemplaza la query sin navegar y avisa a los componentes que la leen. */
export function reemplazarQuery(query: string) {
  window.history.replaceState(null, '', query ? `?${query}` : window.location.pathname);
  window.dispatchEvent(new Event(EVENTO_URL));
}
