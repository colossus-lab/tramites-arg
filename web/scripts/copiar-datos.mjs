// Copia el JSON completo de trámites a las descargas públicas antes de dev/build,
// para no versionar el mismo archivo dos veces (lo genera scripts/exportar_web.py).
import { copyFileSync, mkdirSync } from 'node:fs';

mkdirSync('public/datos', { recursive: true });
copyFileSync('data/tramites.json', 'public/datos/tramites.json');
