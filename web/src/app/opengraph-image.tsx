import { ImageResponse } from 'next/og';
import { agregados } from '@/lib/datos';

export const alt = 'Trámites Arg — los trámites del Estado argentino, en datos';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Imagen() {
  const t = agregados().totales;
  return new ImageResponse(
    (
      <div style={{ width: '100%', height: '100%', display: 'flex', background: '#06090F', color: '#E8ECF4', fontFamily: 'sans-serif' }}>
        <div style={{ width: 14, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, background: '#74ACDF' }} />
          <div style={{ flex: 1, background: '#FFFFFF' }} />
          <div style={{ flex: 1, background: '#74ACDF' }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '64px 72px', flex: 1 }}>
          <div style={{ fontSize: 26, letterSpacing: 4, color: '#8892A8', textTransform: 'uppercase' }}>Trámites Arg · por Colossus Lab</div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: 92, fontWeight: 700, lineHeight: 1, letterSpacing: -3 }}>Argentina,</div>
            <div style={{ fontSize: 92, fontWeight: 700, lineHeight: 1.05, letterSpacing: -3, color: '#F6B40E', fontStyle: 'italic' }}>trámite por trámite.</div>
          </div>
          <div style={{ display: 'flex', gap: 56, fontSize: 30 }}>
            <span><b style={{ color: '#74ACDF' }}>{t.tramites.toLocaleString('es-AR')}</b> trámites</span>
            <span><b style={{ color: '#74ACDF' }}>{t.organismos.toLocaleString('es-AR')}</b> organismos</span>
            <span style={{ color: '#8892A8' }}>Proyecto no oficial</span>
          </div>
        </div>
      </div>
    ),
    size,
  );
}
