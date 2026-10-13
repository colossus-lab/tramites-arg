# Cómo contribuir

¡Gracias por querer sumar! Algunas pautas:

## Correcciones de datos
- Si un trámite tiene un dato mal (organismo, costo, requisito, categoría), abrí un *issue* con el
  link a la fuente oficial que lo respalda.
- Los trámites de alta demanda que no están en TAD se cargan a mano en
  `db/semillas/inventario_etapa1.json`: podés proponer filas nuevas por *pull request*.
- Las reglas de clasificación están en `ingesta/clasificar.py`; los cambios deben venir con un
  test en `tests/test_clasificar.py`.

## Código
1. Levantá la base con `docker compose up -d` y copiá `.env.example` a `.env`.
2. Instalá dependencias: `pip install -r requirements.txt` (y `npm install` en `web/` si tocás la web).
3. Corré los tests antes de abrir el PR: `python -m unittest discover -s tests -t .`
4. Mantené el estilo del código existente y escribí los mensajes de commit en español.

## Scrapers
Las ingestas consultan sitios públicos del Estado. Respetá `robots.txt`, las pausas configuradas
y no aumentes la concurrencia. No agregues fuentes que requieran iniciar sesión.

## Qué no subir
Nunca subas credenciales, archivos `.env`, dumps de la base ni datos personales.
