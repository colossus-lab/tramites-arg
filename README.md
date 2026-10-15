# Trámites Arg

Base abierta y análisis de los **trámites del Estado Nacional argentino**: qué trámites
existen, qué organismo los atiende, cómo se hacen (online, presencial, con qué clave), qué
requisitos piden y cuánto cuestan. Un proyecto de [Colossus Lab](https://colossuslab.org).

**Web:** [tramites-arg.vercel.app](https://tramites-arg.vercel.app) · **Datos:** [descargas](https://tramites-arg.vercel.app/datos) (CC BY 4.0)

> **Proyecto independiente y no oficial.** No está afiliado al Gobierno de la República
> Argentina ni a ninguno de sus organismos. Los datos se construyen automáticamente a partir de
> fuentes públicas y pueden contener errores o estar desactualizados: ante cualquier duda,
> consultá siempre la fuente oficial enlazada en cada trámite.

## Qué hay en este repositorio

| Carpeta | Contenido |
|---|---|
| `db/` | Esquema PostgreSQL, datos base, migraciones y semillas curadas |
| `ingesta/` | Pipeline en Python: ingesta de TAD, detalle de cada trámite, fichas de argentina.gob.ar, extracción de requisitos y costos, clasificación |
| `scripts/` | Backup, control de calidad y exportación de datos para la web |
| `web/` | Sitio de análisis (Next.js, estático) |
| `tests/` | Tests unitarios y de integración |

## Fuentes

- **TAD**: dataset "Plataforma de Trámites a Distancia" de Jefatura de Gabinete en
  [datos.gob.ar](https://datos.gob.ar) y el buscador público de tramitesadistancia.gob.ar.
- **argentina.gob.ar**: fichas públicas de trámites (`/servicio/...`).
- **Inventario curado** de trámites de alta demanda fuera de TAD (DNI, pasaporte, ANSES, ARCA,
  Migraciones, DNRPA…), con la fuente oficial citada en cada fila.

Los scrapers se identifican con un User-Agent que enlaza a este repositorio, respetan
`robots.txt` y sus pausas (10 s entre pedidos a argentina.gob.ar) y no inician sesión en ningún sitio.

## Licencias

- Código: [MIT](LICENSE).
- Datos exportados: [CC BY 4.0](LICENSE-DATA.md), con atribución a las fuentes.

Ver también [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) y
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Puesta en marcha

```bash
cp .env.example .env
docker compose up -d
```

Levanta PostgreSQL 16 en `localhost:5433` (usuario y base `tramites`; la clave sale de `.env`) y aplica
`db/schema.sql`, `db/seed.sql` y `db/organismos_apn.sql` la primera vez que se crea el volumen
(las migraciones de `db/migraciones/` ya están incluidas en `schema.sql`). Para recrear la
base desde cero: `docker compose down -v && docker compose up -d`.

```bash
pip install -r requirements.txt
```

## Ingesta de TAD

```bash
python -m ingesta.tad --dry-run
python -m ingesta.tad
python -m ingesta.tad --desde-dir data/raw/tad/20261012-101500
```

- Resuelve las URLs de las distribuciones 26.1 a 26.5 en el `data.json` de datos.gob.ar y,
  si falla, usa las URLs conocidas. Guarda cada descarga en `data/raw/tad/<fecha>/`.
- Solo la 26.1 (total) es obligatoria. Si falta una opcional, sus campos (aranceles,
  VUCE, Mi Argentina) se arrastran de la corrida anterior, así no se registran cambios falsos.
- Cada `ID_TRAMITE` queda como `fuente` (`tipo = 'csv_tad'`) vinculada a un `tramite`.
  Altas, cambios, bajas y reapariciones quedan en `fuente_evento`; cada corrida, en
  `ingesta_corrida`, con la máxima `FECHA_PUBLICACION_PROD` como medida de frescura.
- Si el CSV trae menos del 80% de los trámites activos, no registra bajas (probable
  archivo truncado) salvo con `--forzar-bajas`.
- Un `ORGANO_RECTOR` sin alias crea un organismo con `revisar = true`. Para mapearlo a uno
  existente, agregar el alias en `organismo_alias` y volver a correr. Los alias de AFIP,
  ANMaC y ANDIS resuelven a ARCA, RENAR y SND por `organismo.sucesor_id`.

## Detalle de TAD y organismo real

`ORGANO_RECTOR` del CSV solo dice el ministerio. El detalle de cada trámite sale de la
API pública del buscador de TAD (`tad2-rest/tipoTramite/{id}` y `.../descripcionTramite/{id}`):

```bash
python -m ingesta.tad_detalle descargar   # ~80 min para 2.500 trámites; reanudable
python -m ingesta.tad_detalle cargar --dry-run
python -m ingesta.tad_detalle cargar
```

- Guarda cada detalle como fuente `api_tad` del mismo trámite (descripción HTML, etiquetas,
  repartición GDE, nivel de acceso, fechas) y usa la descripción corta como `tramite.descripcion`
  salvo que se haya editado a mano.
- El organismo sale de la repartición iniciadora GDE: en `DNDA#MJ` o `INAME#ANMAT`, la sigla
  después del `#`. Si la sigla tiene alias, usa ese organismo; si una etiqueta la nombra
  ("Inspección General de Justicia - IGJ"), crea o reusa ese organismo bajo el ministerio del
  CSV; si no (códigos de ministerios como `MEC` o de ministerios disueltos como `MPYT`), el
  trámite queda en el ministerio del CSV. La ingesta del CSV no pisa este organismo.

## Requisitos y costos desde la descripción

```bash
python -m ingesta.tad_requisitos --dry-run
python -m ingesta.tad_requisitos
```

Extrae de la descripción HTML (ya cargada por `tad_detalle cargar`) los requisitos que
aparecen bajo títulos como "Requisitos", "Documentación obligatoria/opcional", "¿Qué
necesito?" o "Deberá adjuntar", y los montos mencionados en contexto de costo. Es
heurístico: las descripciones no siguen una plantilla. Cada fila queda asociada a su
fuente `api_tad` (`requisito.fuente_id`, `costo.fuente_id`), así una nueva corrida solo
reemplaza lo que salió de esa descripción. Los costos del texto usan el concepto
`arancel (descripción TAD)` y guardan la frase de origen en `costo.detalle`; los del CSV
(`arancel TAD`) no se tocan.

## Inventario curado (trámites fuera de TAD)

```bash
python -m ingesta.inventario --dry-run
python -m ingesta.inventario
```

Carga `db/semillas/inventario_etapa1.json`: 80 trámites de alta demanda y 8 bajas o
migraciones del relevamiento de la Etapa 1. Cada fila tiene una acción explícita: `nuevo` (DNI, pasaporte, ANSES, ARCA, DNRPA,
Migraciones…), `enriquecer` (un trámite TAD que ya existe, por `id_tad`), `incluido_en`
(variante o canal de otra fila, como DNI exprés o antecedentes penales por clave fiscal) u
`omitir` (filas paraguas que agrupan muchos trámites TAD, con su motivo). Para corregir o
agregar trámites se edita el JSON y se vuelve a correr: solo se reescriben las filas que cambiaron.

## Clasificación por categoría

```bash
python -m ingesta.clasificar --dry-run --muestras 10
python -m ingesta.clasificar
```

Asigna la categoría (taxonomía de 30 categorías en `db/seed.sql`) a los trámites que no tienen una manual,
y guarda en `tramite.categoria_regla` qué regla la asignó: `comercio_exterior`, `organismo` y
`palabra_clave` son de confianza alta; `etiqueta` y `ministerio`, de confianza baja. Nunca
pisa `categoria_origen = 'manual'`.

## Fichas de argentina.gob.ar

```bash
python -m ingesta.fichas descargar        # ~5,5 h: robots.txt pide 10 s entre pedidos; reanudable
python -m ingesta.fichas cargar --dry-run
python -m ingesta.fichas cargar
```

Lee las fichas `/servicio/<slug>` del sitemap (las rutas `/tramitar`, `/servicios` y `/buscar` están
bloqueadas por `robots.txt` y no se tocan). Cada ficha se vincula a un trámite existente por número de
TAD, por similitud de nombre dentro del ministerio o por decisión manual en
`db/semillas/fichas_vinculos.json`; si no hay vínculo, crea el trámite. Los casos dudosos quedan en
`data/fichas_candidatos.json` para revisar.

## Variantes y destinatarios

```bash
python -m ingesta.variantes        # agrupa trámites TAD según db/semillas/agrupaciones_tad.json
python -m ingesta.destinatarios    # personas, empresas, profesionales, organismos públicos…
```

## Orden de una actualización completa

```bash
python -m ingesta.tad
python -m ingesta.tad_detalle descargar
python -m ingesta.tad_detalle cargar
python -m ingesta.tad_requisitos
python -m ingesta.fichas descargar
python -m ingesta.fichas cargar
python -m ingesta.inventario
python -m ingesta.variantes
python -m ingesta.clasificar
python -m ingesta.destinatarios
docker compose exec -T db psql -U tramites -d tramites < scripts/calidad.sql
python scripts/exportar_web.py
python scripts/backup.py
```

El detalle de cada paso y la regla de conteo están en [docs/metodologia.md](docs/metodologia.md).

## Web

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run build      # genera todas las páginas estáticas
```

Next.js 16, estática: lee `web/data/` (generado por `scripts/exportar_web.py`) en el build y no
necesita base de datos ni variables de entorno. El diseño editorial está portado de
[OpenArg](https://github.com/colossus-lab/openarg_frontend) (MIT, ColossusLab). Se publica en Vercel
(proyecto `tramites-arg`, directorio raíz `web/`): cada push a `main` despliega solo.

## Backup

`python scripts/backup.py` guarda un `pg_dump` en `backups/` (fuera de git) y conserva los
últimos 10. Restaurar: ver la ayuda del script. Conviene copiar `backups/` a otro disco o nube.

Bases creadas antes de un cambio de esquema se actualizan con los scripts de `db/migraciones/`.

Consultas útiles:

```sql
SELECT * FROM v_tramite_tad ORDER BY id_tad;
SELECT * FROM v_organismo_a_revisar;
SELECT * FROM ingesta_corrida ORDER BY id DESC LIMIT 5;
```

## Tests

```bash
python -m unittest discover -s tests -t .
```

El test de integración crea y borra una base temporal en el Postgres de
`docker compose` (o en `TEST_ADMIN_URL`); si no hay Postgres, se saltea.
