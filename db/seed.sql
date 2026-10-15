-- Datos base: jurisdicción nacional, plataformas, taxonomías y organismos con
-- sucesores (cambios 2024-2026 relevados en la Etapa 1).

BEGIN;

INSERT INTO jurisdiccion (nivel, nombre) VALUES ('nacional', 'República Argentina');

INSERT INTO plataforma (codigo, nombre, jurisdiccion_id, url)
SELECT p.codigo, p.nombre, j.id, p.url
FROM (VALUES
    ('tad',          'Trámites a Distancia (TAD)',   'https://tramitesadistancia.gob.ar'),
    ('mi_argentina', 'Mi Argentina',                 'https://www.argentina.gob.ar/miargentina'),
    ('vuce',         'Ventanilla Única de Comercio Exterior (VUCE)', NULL),
    ('arca',         'ARCA con clave fiscal',        'https://www.arca.gob.ar'),
    ('mi_anses',     'Mi ANSES',                     'https://www.anses.gob.ar'),
    ('radex',        'RaDEx (Migraciones)',          'https://www.migraciones.gob.ar/radex/'),
    ('site_dnrpa',   'SITE / DNRPA',                 'https://www.dnrpa.gov.ar'),
    ('mi_renar',     'Mi RENAR (ex MiAnmac)',        NULL)
) AS p (codigo, nombre, url)
CROSS JOIN jurisdiccion j
WHERE j.nivel = 'nacional';

INSERT INTO categoria (codigo, nombre) VALUES
    ('identidad',             'Identidad y documentación'),
    ('migraciones',           'Migraciones y extranjería'),
    ('seguridad_social',      'Seguridad social y jubilaciones'),
    ('programas_sociales',    'Asignaciones y programas sociales'),
    ('impuestos',             'Impuestos y monotributo'),
    ('trabajo',               'Trabajo y empleo'),
    ('salud',                 'Salud'),
    ('discapacidad',          'Discapacidad'),
    ('educacion',             'Educación'),
    ('vehiculos',             'Vehículos y licencias de conducir'),
    ('transporte',            'Transporte (aéreo, náutico, terrestre)'),
    ('propiedad',             'Propiedad e inmuebles'),
    ('familia',               'Familia y estado civil'),
    ('justicia',              'Justicia y antecedentes'),
    ('armas',                 'Armas y materiales controlados'),
    ('seguridad',             'Seguridad'),
    ('comercio_exterior',     'Comercio exterior'),
    ('empresas',              'Empresas y sociedades'),
    ('organizaciones',        'Organizaciones civiles y economía social'),
    ('propiedad_intelectual', 'Propiedad intelectual'),
    ('consumo',               'Consumo'),
    ('viajes',                'Viajes y trámites consulares'),
    ('telecomunicaciones',    'Telecomunicaciones e internet'),
    ('agro',                  'Agro y alimentos'),
    ('ambiente',              'Ambiente'),
    ('cultura',               'Cultura'),
    ('finanzas',              'Finanzas y seguros'),
    ('transversal',           'Transversal (turnos, credenciales, consultas)'),
    -- Agregadas al clasificar TAD: la taxonomía del informe no las tenía.
    ('energia',               'Energía'),
    ('ciencia_tecnologia',    'Ciencia y tecnología'),
    -- Agregadas con las fichas de argentina.gob.ar.
    ('gestion_publica',       'Gestión pública y relación con el Estado'),
    ('turismo_deporte',       'Turismo y deporte');

INSERT INTO hecho_vital (codigo, nombre) VALUES
    ('nacer',        'Nacer'),
    ('estudiar',     'Estudiar'),
    ('trabajar',     'Trabajar'),
    ('emprender',    'Emprender'),
    ('migrar',       'Migrar a la Argentina'),
    ('viajar',       'Viajar al exterior'),
    ('mudarse',      'Mudarse'),
    ('comprar_auto', 'Comprar un auto'),
    ('jubilarse',    'Jubilarse'),
    ('fallecimiento', 'Fallecimiento de un familiar');

-- Organismos con cambios institucionales 2024-2026 --------------------------

INSERT INTO organismo (jurisdiccion_id, nombre_oficial, sigla, tipo, vigente_desde, vigente_hasta,
                       norma_creacion, norma_disolucion, dominios_web)
SELECT j.id, o.nombre, o.sigla, o.tipo, o.desde::date, o.hasta::date, o.creacion, o.disolucion, o.dominios::text[]
FROM (VALUES
    ('Ministerio de Salud', 'MSAL', 'ministerio', NULL, NULL, NULL, NULL, '{argentina.gob.ar/salud}'),
    ('Ministerio de Seguridad Nacional', 'MSN', 'ministerio', NULL, NULL, NULL, NULL, '{argentina.gob.ar/seguridad}'),
    ('Administración Federal de Ingresos Públicos', 'AFIP', 'ente_autarquico', NULL, '2024-10-25',
        NULL, 'Decreto 953/2024', '{afip.gob.ar}'),
    ('Agencia de Recaudación y Control Aduanero', 'ARCA', 'ente_autarquico', '2024-10-25', NULL,
        'Decreto 953/2024; estructura por Decreto 13/2025', NULL, '{arca.gob.ar,afip.gob.ar}'),
    ('Agencia Nacional de Materiales Controlados', 'ANMAC', 'ente_descentralizado', NULL, '2025-07-01',
        NULL, 'Decreto 445/2025', '{}'),
    ('Registro Nacional de Armas', 'RENAR', 'organismo_desconcentrado', '2025-07-01', NULL,
        'Decreto 445/2025; reorganizado por Decreto 770/2026', NULL, '{}'),
    ('Agencia Nacional de Discapacidad', 'ANDIS', 'ente_descentralizado', NULL, '2026-01-02',
        NULL, 'DNU 942/2025', '{}'),
    ('Secretaría Nacional de Discapacidad', 'SND', 'secretaria', NULL, NULL,
        'DNU 942/2025; estructura por Decreto 27/2026', NULL, '{}')
) AS o (nombre, sigla, tipo, desde, hasta, creacion, disolucion, dominios)
CROSS JOIN jurisdiccion j
WHERE j.nivel = 'nacional';

UPDATE organismo SET sucesor_id = (SELECT id FROM organismo WHERE sigla = 'ARCA')  WHERE sigla = 'AFIP';
UPDATE organismo SET sucesor_id = (SELECT id FROM organismo WHERE sigla = 'RENAR') WHERE sigla = 'ANMAC';
UPDATE organismo SET sucesor_id = (SELECT id FROM organismo WHERE sigla = 'SND')   WHERE sigla = 'ANDIS';
UPDATE organismo SET padre_id   = (SELECT id FROM organismo WHERE sigla = 'MSN')   WHERE sigla = 'RENAR';
UPDATE organismo SET padre_id   = (SELECT id FROM organismo WHERE sigla = 'MSAL')  WHERE sigla = 'SND';

-- Alias: nombre oficial y sigla de cada organismo cargado, más variantes conocidas.
INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
SELECT normalizar_texto(nombre_oficial), nombre_oficial, id, 'seed' FROM organismo
UNION ALL
SELECT normalizar_texto(sigla), sigla, id, 'seed' FROM organismo WHERE sigla IS NOT NULL
ON CONFLICT (alias_normalizado) DO NOTHING;

INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
SELECT normalizar_texto(a.alias), a.alias, o.id, 'seed'
FROM (VALUES
    ('ANMaC', 'ANMAC'),
    ('Registro Nacional de Armas (RENAR)', 'RENAR'),
    ('Agencia Nacional de Discapacidad (ANDIS)', 'ANDIS'),
    ('Administración Federal de Ingresos Públicos (AFIP)', 'AFIP'),
    ('Agencia de Recaudación y Control Aduanero (ARCA)', 'ARCA')
) AS a (alias, sigla)
JOIN organismo o ON o.sigla = a.sigla
ON CONFLICT (alias_normalizado) DO NOTHING;

COMMIT;
