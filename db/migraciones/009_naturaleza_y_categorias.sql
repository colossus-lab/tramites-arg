-- Servicios de consulta (ver el padrón, el calendario de pagos, el estado de un expediente):
-- quedan en la base pero no cuentan como trámite. Y dos categorías que aparecieron con las
-- fichas de argentina.gob.ar.
BEGIN;
ALTER TABLE tramite
    ADD COLUMN naturaleza text NOT NULL DEFAULT 'tramite' CHECK (naturaleza IN ('tramite', 'consulta')),
    ADD COLUMN naturaleza_origen text CHECK (naturaleza_origen IN ('manual', 'auto'));
INSERT INTO categoria (codigo, nombre) VALUES
    ('gestion_publica', 'Gestión pública y relación con el Estado'),
    ('turismo_deporte', 'Turismo y deporte')
ON CONFLICT (codigo) DO NOTHING;
COMMIT;
