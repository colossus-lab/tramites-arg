# Metodología

Resumen técnico de cómo se construye la base. La versión para el público está en la página
`/metodologia` de la web.

## Regla de conteo

Un **trámite** es una solicitud ante un organismo con un resultado propio (inscribirse, renovar,
pedir un certificado, dar de baja). Cuando lo único que cambia es el tipo de persona (humana o
jurídica), el tipo de obra, el plazo o el precio, es **un solo trámite con variantes**
(`tramite_variante`).

No cuentan como trámites en los análisis:

- los `fusionado` (variantes de otro trámite; `reemplazado_por_id` apunta al canónico);
- los `baja` y `migrado`;
- los trámites de prueba del catálogo de TAD (nombres "Testing de performance", "Prueba adm…");
- los servicios de consulta (`tramite.naturaleza = 'consulta'`): ver el padrón, el calendario de pagos o el estado
  de un expediente sin pedirle nada al organismo. Las consultas formales que reciben una respuesta propia
  ("Consulta de clasificación de productos") sí son trámites. Regla en `ingesta/clasificar.py` (`naturaleza`).

## Fuentes y orden de carga

| Paso | Módulo | Fuente | Qué aporta |
|---|---|---|---|
| 1 | `ingesta.tad` | CSV del dataset JGM 26 en datos.gob.ar | Trámites TAD, ministerio, arancel, validadores de identidad, VUCE y Mi Argentina |
| 2 | `ingesta.tad_detalle` | API pública `tad2-rest` del buscador de TAD | Descripción, repartición GDE (organismo real), etiquetas |
| 3 | `ingesta.tad_requisitos` | Descripción HTML de TAD | Requisitos y costos extraídos |
| 4 | `ingesta.fichas` | Fichas `/servicio/` de argentina.gob.ar | Destinatarios, requisitos, costos, canales, trámites presenciales |
| 5 | `ingesta.inventario` | `db/semillas/inventario_etapa1.json` | Trámites de alta demanda fuera de TAD, con variantes y normas |
| 6 | `ingesta.variantes` | `db/semillas/agrupaciones_tad.json` | Agrupa trámites TAD que son variantes de uno |
| 7 | `ingesta.clasificar` | Reglas | Categoría (con la regla que la asignó) |
| 8 | `ingesta.destinatarios` | Reglas | Destinatarios (con la regla que los asignó) |
| 9 | `scripts/exportar_web.py` | Base | Archivos de la web y descargas |

Cada ingesta es idempotente: compara el hash del registro normalizado y solo escribe lo que
cambió. Las altas, cambios, bajas y reapariciones quedan en `fuente_evento`, y cada corrida en
`ingesta_corrida`.

## Vínculo entre fuentes

- **TAD ↔ ficha:** por el número de TAD que aparece en el botón de inicio de la ficha
  (`detalle-tipo?id=`, `idTipoTramite=`, `configuracionInicioTipoTramite/`).
- **Por nombre:** similitud trigram (`pg_trgm`) dentro del mismo ministerio. Desde 0,75 se vincula
  automáticamente; entre 0,45 y 0,75 va a revisión manual (`data/fichas_candidatos.json`), y la
  decisión se guarda en `db/semillas/fichas_vinculos.json`.
- **Sin vínculo:** la ficha crea un trámite nuevo.

## Organismos

- El organismo sale de la repartición GDE iniciadora (`DNDA#MJ`, `INAME#ANMAT`): primero la
  repartición completa, después la sigla después del `#`, después una etiqueta "Nombre - SIGLA".
  Si nada coincide, el trámite queda en el ministerio del CSV.
- En las fichas, sale de las migas de navegación (del elemento más específico al más general).
- Los cambios institucionales se modelan con `organismo.sucesor_id`; `organismo_actual()` sigue
  la cadena.

## Clasificación

Reglas en `ingesta/clasificar.py` y `ingesta/destinatarios.py`, con tests. Prioridad de la
categoría: comercio exterior por nombre → organismo → palabras clave → etiqueta temática de TAD →
ministerio. `categoria_regla` permite auditar las de baja confianza (`etiqueta`, `ministerio`).
Ninguna regla automática pisa una asignación manual.

Canales de las fichas: botones de inicio (plataforma por dominio) y, si no hay, el texto de "¿Cómo hago?"
(TAD, Mi Argentina, plataforma web, correo electrónico, correo postal, mesa de entradas, turnos). El canal TAD
de un trámite vinculado lo aporta el CSV y no se duplica.

## Limitaciones conocidas

- La extracción de requisitos y costos del HTML es heurística.
- Muchos trámites de TAD definen sus documentos dentro del formulario (solo visible con sesión),
  así que no tienen requisitos extraídos.
- La marca "no arancelado" del CSV de TAD no es confiable: hay trámites así marcados cuya
  descripción o ficha informa un monto. La web muestra todas las fuentes de costo.
- Cobertura: solo Estado Nacional.
