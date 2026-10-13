-- Organismos de primer nivel de la APN tal como los nombra ORGANO_RECTOR en los
-- CSV de TAD. Idempotente: si el organismo ya existe (por alias) lo completa y
-- le quita la marca de revisión; si no, lo crea con su alias.

BEGIN;

DO $$
DECLARE
    o record;
    v_id integer;
    v_nacion integer := (SELECT id FROM jurisdiccion WHERE nivel = 'nacional');
BEGIN
    FOR o IN
        SELECT * FROM (VALUES
            ('Ministerio de Economía', 'MECON', 'ministerio'),
            ('Jefatura de Gabinete de Ministros', 'JGM', 'ministerio'),
            ('Ministerio de Capital Humano', 'MCH', 'ministerio'),
            ('Ministerio de Justicia', 'MJ', 'ministerio'),
            ('Ministerio de Relaciones Exteriores, Comercio Internacional y Culto', 'MRECIC', 'ministerio'),
            ('Ministerio de Defensa', 'MD', 'ministerio'),
            ('Ministerio de Desregulación y Transformación del Estado', 'MDYTE', 'ministerio'),
            ('Ministerio del Interior', 'MI', 'ministerio'),
            ('Secretaría Legal y Técnica', 'SLYT', 'secretaria'),
            ('Secretaría General', 'SGP', 'secretaria'),
            ('Secretaría de Cultura', NULL, 'secretaria'),
            ('Secretaría de Comunicación y Medios', NULL, 'secretaria'),
            ('Sindicatura General de la Nación', 'SIGEN', 'ente_autarquico')
        ) AS t (nombre, sigla, tipo)
    LOOP
        SELECT organismo_id INTO v_id FROM organismo_alias WHERE alias_normalizado = normalizar_texto(o.nombre);
        IF v_id IS NULL THEN
            INSERT INTO organismo (jurisdiccion_id, nombre_oficial, sigla, tipo)
            VALUES (v_nacion, o.nombre, o.sigla, o.tipo)
            RETURNING id INTO v_id;
            INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
            VALUES (normalizar_texto(o.nombre), o.nombre, v_id, 'seed');
        ELSE
            UPDATE organismo
            SET nombre_oficial = o.nombre, sigla = o.sigla, tipo = o.tipo, revisar = false
            WHERE id = v_id;
        END IF;
        IF o.sigla IS NOT NULL THEN
            INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
            VALUES (normalizar_texto(o.sigla), o.sigla, v_id, 'seed')
            ON CONFLICT (alias_normalizado) DO NOTHING;
        END IF;
    END LOOP;
END
$$;

-- Organismos cuyo código de repartición GDE no coincide con la sigla de las
-- etiquetas de TAD (o que no tienen etiqueta), así que ingesta.tad_detalle no
-- los reconoce solo. El padre es el ministerio que informa ORGANO_RECTOR para
-- sus trámites.
DO $$
DECLARE
    o record;
    v_id integer;
    v_nacion integer := (SELECT id FROM jurisdiccion WHERE nivel = 'nacional');
BEGIN
    FOR o IN
        SELECT * FROM (VALUES
            ('Administración de Parques Nacionales', 'APN', 'ente_descentralizado', 'JGM', 'APNAC'),
            ('Agencia Nacional de Promoción de la Investigación, el Desarrollo Tecnológico y la Innovación',
                'Agencia I+D+i', 'ente_descentralizado', 'JGM', 'ANPIDTYI'),
            ('Secretaría de Asuntos Estratégicos', 'SAE', 'secretaria', 'JGM', 'SAE'),
            ('Instituto de Ayuda Financiera para Pago de Retiros y Pensiones Militares', 'IAFPRPM',
                'ente_descentralizado', 'MD', 'IAF'),
            ('Caja de Retiros, Jubilaciones y Pensiones de la Policía Federal', 'CRJPPF',
                'ente_descentralizado', 'MSN', 'CRJYPPF'),
            ('Agencia Federal de Emergencias', 'AFE', NULL, 'MSN', 'AFE'),
            ('Ente Nacional Regulador del Gas y la Electricidad', 'ENREGE', 'ente_autarquico', 'MECON', 'ENREGE'),
            ('Banco de Inversión y Comercio Exterior', 'BICE', 'empresa_estatal', 'MECON', 'BICE'),
            ('Junta de Seguridad en el Transporte', 'JST', 'ente_descentralizado', 'MECON', 'JST'),
            ('Instituto Nacional Central Único Coordinador de Ablación e Implante', 'INCUCAI',
                'ente_descentralizado', 'MSAL', 'INCUCAI'),
            ('Consejo Nacional de Coordinación de Políticas Sociales', 'CNCPS', NULL, 'MCH', 'CNCPS'),
            -- Organismos del inventario de la Etapa 1. Para dependencias de un ministerio
            -- el código GDE es la repartición completa ("DNDA#MJ"), no solo la sigla.
            ('Registro Nacional de Reincidencia', 'RNR', 'registro', 'MJ', 'RNR'),
            ('Dirección Nacional de los Registros Nacionales de la Propiedad del Automotor y de Créditos Prendarios',
                'DNRPA', 'registro', 'MJ', 'DNRPA'),
            ('Dirección Nacional del Derecho de Autor', 'DNDA', 'registro', 'MJ', 'DNDA#MJ'),
            ('Instituto Nacional de la Propiedad Industrial', 'INPI', 'ente_autarquico', 'MECON', 'INPI'),
            ('Secretaría de Industria y Comercio', 'SIYC', 'secretaria', 'MECON', 'SIYC'),
            ('Secretaría de Trabajo, Empleo y Seguridad Social', 'STEYSS', 'secretaria', 'MCH', 'STEYSS'),
            ('NIC Argentina (Dirección Nacional del Registro de Dominios de Internet)', 'NIC Argentina',
                'registro', 'SLYT', 'DNRDI#SLYT')
        ) AS t (nombre, sigla, tipo, padre_sigla, codigo_gde)
    LOOP
        SELECT organismo_id INTO v_id FROM organismo_alias WHERE alias_normalizado = normalizar_texto(o.nombre);
        IF v_id IS NULL THEN
            INSERT INTO organismo (jurisdiccion_id, nombre_oficial, sigla, tipo, padre_id)
            VALUES (v_nacion, o.nombre, o.sigla, o.tipo,
                    (SELECT id FROM organismo WHERE sigla = o.padre_sigla AND vigente_hasta IS NULL))
            RETURNING id INTO v_id;
        ELSE
            UPDATE organismo
            SET sigla = o.sigla, tipo = o.tipo, revisar = false,
                padre_id = (SELECT id FROM organismo WHERE sigla = o.padre_sigla AND vigente_hasta IS NULL)
            WHERE id = v_id;
        END IF;
        INSERT INTO organismo_alias (alias_normalizado, alias_original, organismo_id, origen)
        VALUES (normalizar_texto(o.nombre), o.nombre, v_id, 'seed'),
               (normalizar_texto(o.sigla), o.sigla, v_id, 'seed'),
               (normalizar_texto(o.codigo_gde), o.codigo_gde, v_id, 'gde')
        ON CONFLICT (alias_normalizado) DO NOTHING;
    END LOOP;
END
$$;

COMMIT;
