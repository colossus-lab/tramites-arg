import type { Metadata, Viewport } from 'next';

import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource-variable/familjen-grotesk';

import './globals.css';
import './tramites.css';
import Colophon from '@/components/Colophon';
import Topbar from '@/components/Topbar';
import { meta } from '@/lib/datos';
import { fecha, SITIO } from '@/lib/formato';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#06090F' },
    { media: '(prefers-color-scheme: light)', color: '#F2EDE2' },
  ],
};

const DESCRIPCION =
  'Base abierta y análisis de los trámites del Estado Nacional argentino: qué organismo los atiende, ' +
  'cómo se hacen, qué piden y cuánto cuestan. Proyecto independiente y no oficial de Colossus Lab.';

export const metadata: Metadata = {
  metadataBase: new URL(SITIO.url),
  title: { default: 'Trámites Arg — los trámites del Estado argentino, en datos', template: '%s · Trámites Arg' },
  description: DESCRIPCION,
  keywords: ['trámites', 'Argentina', 'Estado nacional', 'datos abiertos', 'TAD', 'Trámites a Distancia',
             'organismos públicos', 'Colossus Lab'],
  openGraph: { type: 'website', siteName: 'Trámites Arg', locale: 'es_AR', description: DESCRIPCION },
  twitter: { card: 'summary_large_image' },
  alternates: { canonical: '/' },
};

// Aplica el tema guardado antes de pintar, para evitar el parpadeo (mismo patrón que OpenArg).
const SCRIPT_TEMA =
  "(function(){try{var t=localStorage.getItem('tramitesarg-theme');var theme;if(t==='light'||t==='dark'){theme=t}" +
  "else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches){theme='light'}else{theme='dark'}" +
  "document.documentElement.setAttribute('data-theme',theme)}catch(e){document.documentElement.setAttribute('data-theme','dark')}})();";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es-AR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_TEMA }} />
      </head>
      <body>
        <div className="ed-page">
          <a href="#contenido" className="ta-saltar">Saltar al contenido</a>
          <Topbar />
          <main id="contenido">{children}</main>
          <Colophon fechaCorte={fecha(meta().fecha_corte)} />
        </div>
      </body>
    </html>
  );
}
