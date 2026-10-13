import Link from 'next/link';

export default function NoEncontrado() {
  return (
    <div className="ed-container">
      <header className="ta-cabecera" style={{ paddingBottom: '6rem' }}>
        <p className="ed-eyebrow"><span className="ed-eyebrow-num">404</span><span>No encontrado</span></p>
        <h1 className="ed-display">Este trámite no está en la base.</h1>
        <p className="ed-lead">Puede que haya cambiado de nombre o que se haya dado de baja.</p>
        <p className="ta-mas">
          <Link href="/tramites" className="ed-textlink"><span className="ed-textlink-arrow">→</span><span>Buscar un trámite</span></Link>
          <Link href="/" className="ed-textlink"><span className="ed-textlink-arrow">→</span><span>Ir al inicio</span></Link>
        </p>
      </header>
    </div>
  );
}
