-- Base de trámites del Estado argentino.
-- Etapa 1: Gobierno Nacional. Jurisdicciones y organismos están modelados como
-- jerarquías con historial para sumar provincias y municipios sin rediseñar.
-- Requiere PostgreSQL 16+.

BEGIN;

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Funciones auxiliares ------------------------------------------------------

-- Clave de comparación de textos: mayúsculas, sin tildes ni puntuación.
-- Es la única definición de normalización; la ingesta la llama desde SQL.
CREATE FUNCTION normalizar_texto(t text) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT NULLIF(btrim(regexp_replace(upper(public.unaccent(t)), '[^A-Z0-9]+', ' ', 'g')), '')
$$;

CREATE FUNCTION tocar_actualizado_en() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.actualizado_en := now();
    RETURN NEW;
END
$$;

-- Jurisdicciones y organismos ----------------------------------------------

CREATE TABLE jurisdiccion (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nivel          text NOT NULL CHECK (nivel IN ('nacional', 'provincial', 'departamental', 'municipal')),
    nombre         text NOT NULL,
    codigo_georef  text UNIQUE,  -- id de la API Georef de datos.gob.ar; NULL para la Nación
    padre_id       integer REFERENCES jurisdiccion (id),
    CHECK ((nivel = 'nacional') = (padre_id IS NULL))
);

CREATE TABLE organismo (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    jurisdiccion_id   integer NOT NULL REFERENCES jurisdiccion (id),
    nombre_oficial    text NOT NULL,
    sigla             text,
    tipo              text CHECK (tipo IN ('ministerio', 'secretaria', 'ente_autarquico', 'ente_descentralizado',
                                           'organismo_desconcentrado', 'empresa_estatal', 'registro',
                                           'consulado', 'otro')),
    padre_id          integer REFERENCES organismo (id),
    sucesor_id        integer REFERENCES organismo (id),  -- AFIP -> ARCA, ANMaC -> RENAR, ANDIS -> SND
    vigente_desde     date,
    vigente_hasta     date,
    norma_creacion    text,
    norma_disolucion  text,
    dominios_web      text[] NOT NULL DEFAULT '{}',
    revisar           boolean NOT NULL DEFAULT false,  -- alta automática pendiente de revisión humana
    creado_en         timestamptz NOT NULL DEFAULT now(),
    CHECK (sucesor_id IS DISTINCT FROM id),
    CHECK (vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde)
);

CREATE UNIQUE INDEX organismo_sigla_vigente_uq
    ON organismo (jurisdiccion_id, sigla)
    WHERE sigla IS NOT NULL AND vigente_hasta IS NULL;
CREATE INDEX organismo_padre_idx ON organismo (padre_id);

-- Cómo nombra cada fuente a un organismo. Un alias puede apuntar a un organismo
-- disuelto: organismo_actual() sigue la cadena de sucesores.
CREATE TABLE organismo_alias (
    alias_normalizado  text PRIMARY KEY,  -- normalizar_texto(alias_original)
    alias_original     text NOT NULL,
    organismo_id       integer NOT NULL REFERENCES organismo (id),
    origen             text NOT NULL DEFAULT 'manual'  -- manual | seed | csv_tad | ...
);
CREATE INDEX organismo_alias_organismo_idx ON organismo_alias (organismo_id);

CREATE FUNCTION organismo_actual(p_id integer) RETURNS integer
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE cadena (id, sucesor_id, profundidad) AS (
        SELECT id, sucesor_id, 0 FROM organismo WHERE id = p_id
        UNION ALL
        SELECT o.id, o.sucesor_id, c.profundidad + 1
        FROM organismo o
        JOIN cadena c ON o.id = c.sucesor_id
        WHERE c.profundidad < 20  -- corta ciclos accidentales
    )
    SELECT id FROM cadena ORDER BY profundidad DESC LIMIT 1
$$;

-- Taxonomías ---------------------------------------------------------------

CREATE TABLE categoria (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo    text NOT NULL UNIQUE,
    nombre    text NOT NULL,
    padre_id  integer REFERENCES categoria (id)
);

CREATE TABLE hecho_vital (
    id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo  text NOT NULL UNIQUE,
    nombre  text NOT NULL
);

CREATE TABLE plataforma (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo           text NOT NULL UNIQUE,
    nombre           text NOT NULL,
    jurisdiccion_id  integer NOT NULL REFERENCES jurisdiccion (id),
    url              text
);

-- Trámites -----------------------------------------------------------------

-- Una fila por trámite "de cara al usuario". Las variantes de plazo, precio o
-- tipo de persona van en tramite_variante y no cuentan como trámite nuevo.
CREATE TABLE tramite (
    id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                       text NOT NULL UNIQUE,
    nombre_ciudadano           text NOT NULL,
    nombre_oficial             text,
    descripcion                text,
    organismo_id               integer NOT NULL REFERENCES organismo (id),
    categoria_id               integer REFERENCES categoria (id),
    estado                     text NOT NULL DEFAULT 'vigente'
                               CHECK (estado IN ('vigente', 'migrado', 'baja', 'suspendido', 'fusionado')),
    reemplazado_por_id         uuid REFERENCES tramite (id),
    norma_base                 text,
    fecha_ultima_verificacion  date,
    creado_en                  timestamptz NOT NULL DEFAULT now(),
    actualizado_en             timestamptz NOT NULL DEFAULT now(),
    CHECK (estado NOT IN ('migrado', 'fusionado') OR reemplazado_por_id IS NOT NULL),
    CHECK (reemplazado_por_id IS DISTINCT FROM id)
);

CREATE INDEX tramite_organismo_idx ON tramite (organismo_id);
CREATE INDEX tramite_categoria_idx ON tramite (categoria_id);
CREATE INDEX tramite_estado_idx ON tramite (estado);
CREATE INDEX tramite_nombre_trgm_idx ON tramite USING gin (nombre_ciudadano gin_trgm_ops);

CREATE TRIGGER tramite_actualizado_en
    BEFORE UPDATE ON tramite
    FOR EACH ROW EXECUTE FUNCTION tocar_actualizado_en();

CREATE TABLE tramite_variante (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tramite_id        uuid NOT NULL REFERENCES tramite (id) ON DELETE CASCADE,
    nombre            text NOT NULL,  -- "exprés", "persona jurídica", "extra Mercosur"
    plazo_resolucion  text,
    UNIQUE (tramite_id, nombre)
);

CREATE TABLE tramite_destinatario (
    tramite_id  uuid NOT NULL REFERENCES tramite (id) ON DELETE CASCADE,
    tipo        text NOT NULL CHECK (tipo IN ('pf_ciudadano', 'pf_extranjero_residente', 'pf_no_residente',
                                              'empresa', 'emprendedor', 'organizacion_civil',
                                              'cooperativa_mutual', 'organismo_publico', 'profesional')),
    PRIMARY KEY (tramite_id, tipo)
);

CREATE TABLE tramite_hecho_vital (
    tramite_id      uuid NOT NULL REFERENCES tramite (id) ON DELETE CASCADE,
    hecho_vital_id  integer NOT NULL REFERENCES hecho_vital (id),
    PRIMARY KEY (tramite_id, hecho_vital_id)
);

-- Fuentes y trazabilidad ---------------------------------------------------

-- Cada registro externo del que sale un trámite. (tipo, id_externo) es la
-- clave de la fuente: para TAD, id_externo = ID_TRAMITE.
CREATE TABLE fuente (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tramite_id       uuid REFERENCES tramite (id) ON DELETE SET NULL,
    tipo             text NOT NULL CHECK (tipo IN ('csv_tad', 'api_tad', 'ficha_argentina_gob_ar', 'sitio_organismo',
                                                   'boletin_oficial', 'acceso_informacion', 'manual')),
    id_externo       text,
    url              text,
    datos            jsonb,  -- último registro normalizado tal como vino de la fuente
    hash_contenido   text,   -- sha256 de datos; detecta cambios entre corridas
    primera_captura  timestamptz NOT NULL DEFAULT now(),
    fecha_captura    timestamptz NOT NULL DEFAULT now(),  -- última vez que se vio en la fuente
    fecha_cambio     timestamptz,                         -- último cambio de hash_contenido
    activo           boolean NOT NULL DEFAULT true,       -- false = ya no figura en la fuente
    UNIQUE (tipo, id_externo)
);
CREATE INDEX fuente_tramite_idx ON fuente (tramite_id);

CREATE TABLE ingesta_corrida (
    id                     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fuente_tipo            text NOT NULL,
    iniciada_en            timestamptz NOT NULL DEFAULT now(),
    finalizada_en          timestamptz,
    estado                 text NOT NULL DEFAULT 'en_curso'
                           CHECK (estado IN ('en_curso', 'ok', 'error', 'simulacion')),
    archivos               jsonb NOT NULL DEFAULT '[]',  -- [{distribucion, url, sha256, bytes, filas}]
    filas_leidas           integer,
    altas                  integer,
    cambios                integer,
    bajas                  integer,
    reapariciones          integer,
    sin_cambios            integer,
    max_fecha_publicacion  date,  -- frescura real del dataset (los metadatos no son confiables)
    advertencias           jsonb NOT NULL DEFAULT '[]',
    error                  text
);

CREATE TABLE fuente_evento (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    corrida_id     integer NOT NULL REFERENCES ingesta_corrida (id),
    fuente_id      integer NOT NULL REFERENCES fuente (id) ON DELETE CASCADE,
    evento         text NOT NULL CHECK (evento IN ('alta', 'cambio', 'baja', 'reaparicion')),
    hash_anterior  text,
    hash_nuevo     text,
    diferencias    jsonb,  -- {campo: [antes, después]}
    creado_en      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX fuente_evento_fuente_idx ON fuente_evento (fuente_id);
CREATE INDEX fuente_evento_corrida_idx ON fuente_evento (corrida_id);

-- Canales, autenticación, requisitos y costos --------------------------------

CREATE TABLE canal (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tramite_id        uuid NOT NULL REFERENCES tramite (id) ON DELETE CASCADE,
    variante_id       integer REFERENCES tramite_variante (id) ON DELETE CASCADE,
    modalidad         text NOT NULL CHECK (modalidad IN ('online', 'presencial', 'mixta', 'telefonica',
                                                         'consular', 'correo')),
    plataforma_id     integer REFERENCES plataforma (id),
    url_inicio        text,
    requiere_turno    boolean,
    acepta_apoderado  boolean,
    activo            boolean NOT NULL DEFAULT true,
    fuente_id         integer REFERENCES fuente (id)  -- canal mantenido por una ingesta; NULL = carga manual
);
CREATE INDEX canal_tramite_idx ON canal (tramite_id);
CREATE UNIQUE INDEX canal_fuente_plataforma_uq ON canal (fuente_id, plataforma_id) WHERE fuente_id IS NOT NULL;

CREATE TABLE canal_autenticacion (
    canal_id      integer NOT NULL REFERENCES canal (id) ON DELETE CASCADE,
    metodo        text NOT NULL CHECK (metodo IN ('sin_autenticacion', 'mi_argentina', 'mi_argentina_validado',
                                                  'clave_fiscal', 'css_anses', 'dni_tramite',
                                                  'nic_no_residente', 'firma_digital', 'otro')),
    nivel_minimo  smallint CHECK (nivel_minimo BETWEEN 1 AND 4),
    detalle       text,  -- texto original de la fuente
    PRIMARY KEY (canal_id, metodo)
);

CREATE TABLE requisito (
    id                 integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tramite_id         uuid NOT NULL REFERENCES tramite (id) ON DELETE CASCADE,
    variante_id        integer REFERENCES tramite_variante (id) ON DELETE CASCADE,
    tipo               text NOT NULL CHECK (tipo IN ('documento', 'condicion', 'pago_previo', 'tramite_previo')),
    descripcion        text NOT NULL,
    tramite_previo_id  uuid REFERENCES tramite (id),  -- grafo de dependencias (radicación -> DNI extranjero)
    orden              smallint,
    seccion            text,     -- título bajo el que figura ("Personas jurídicas", "Documentación opcional")
    obligatorio        boolean NOT NULL DEFAULT true,
    fuente_id          integer REFERENCES fuente (id) ON DELETE CASCADE,  -- extracción automática; NULL = carga manual
    CHECK (tipo <> 'tramite_previo' OR tramite_previo_id IS NOT NULL)
);
CREATE INDEX requisito_tramite_idx ON requisito (tramite_id);
CREATE INDEX requisito_fuente_idx ON requisito (fuente_id);

-- Historial de aranceles: un cambio de monto cierra la fila vigente y abre otra.
CREATE TABLE costo (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tramite_id      uuid NOT NULL REFERENCES tramite (id) ON DELETE CASCADE,
    variante_id     integer REFERENCES tramite_variante (id) ON DELETE CASCADE,
    concepto        text NOT NULL DEFAULT 'arancel',
    gratuito        boolean NOT NULL,
    monto_min       numeric(16, 2),
    monto_max       numeric(16, 2),
    monto_promedio  numeric(16, 2),
    unidad          text NOT NULL DEFAULT 'ARS'
                    CHECK (unidad IN ('ARS', 'USD', 'EUR', 'UMSM', 'UC_CONSULAR', 'otro')),
    norma           text,
    vigente_desde   date NOT NULL DEFAULT current_date,
    vigente_hasta   date,
    fuente_id       integer REFERENCES fuente (id),
    detalle         text,  -- texto de origen cuando el costo se extrajo de una descripción
    CHECK (NOT gratuito OR (monto_min IS NULL AND monto_max IS NULL AND monto_promedio IS NULL)),
    CHECK (monto_min IS NULL OR monto_max IS NULL OR monto_min <= monto_max),
    CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde)
);
CREATE INDEX costo_fuente_idx ON costo (fuente_id);
-- Un solo costo vigente por concepto; cada fuente lleva el suyo, así dos fuentes
-- consolidadas en el mismo trámite no chocan.
CREATE UNIQUE INDEX costo_vigente_uq
    ON costo (tramite_id, COALESCE(variante_id, 0), concepto, unidad, COALESCE(fuente_id, 0))
    WHERE vigente_hasta IS NULL;

-- Vistas -------------------------------------------------------------------

CREATE VIEW v_tramite_tad AS
SELECT
    t.id                                       AS tramite_id,
    f.id_externo::integer                      AS id_tad,
    t.nombre_ciudadano,
    t.estado,
    o.sigla                                    AS organismo_sigla,
    o.nombre_oficial                           AS organismo,
    f.datos ->> 'organo_rector'                AS organo_rector_tad,
    (f.datos ->> 'fecha_publicacion')::date    AS fecha_publicacion,
    c.gratuito,
    c.monto_min,
    c.monto_max,
    f.url,
    f.activo                                   AS figura_en_tad,
    f.fecha_captura                            AS visto_por_ultima_vez
FROM fuente f
JOIN tramite t ON t.id = f.tramite_id
JOIN organismo o ON o.id = t.organismo_id
LEFT JOIN costo c ON c.fuente_id = f.id AND c.vigente_hasta IS NULL
WHERE f.tipo = 'csv_tad';

-- Organismos creados automáticamente por una ingesta, para revisar y mapear.
CREATE VIEW v_organismo_a_revisar AS
SELECT
    o.id,
    o.nombre_oficial,
    (SELECT count(*) FROM tramite t WHERE t.organismo_id = o.id) AS tramites,
    (SELECT array_agg(a.alias_original ORDER BY a.alias_original)
     FROM organismo_alias a WHERE a.organismo_id = o.id)          AS alias
FROM organismo o
WHERE o.revisar
ORDER BY tramites DESC, o.nombre_oficial;

COMMIT;
