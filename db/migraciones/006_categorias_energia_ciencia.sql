-- Categorías que faltaban en la taxonomía del informe (detectadas al clasificar TAD).
BEGIN;
INSERT INTO categoria (codigo, nombre) VALUES
    ('energia', 'Energía'),
    ('ciencia_tecnologia', 'Ciencia y tecnología')
ON CONFLICT (codigo) DO NOTHING;
COMMIT;
