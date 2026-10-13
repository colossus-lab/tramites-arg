"""Exporta la base a los archivos estáticos que usa la web (web/data) y a las descargas públicas
(web/public/datos).

    python scripts/exportar_web.py

Solo exporta campos públicos (ver CAMPOS_TRAMITE): nada de hashes, datos crudos de las fuentes,
IDs internos ni advertencias de las corridas. Las descripciones HTML se sanitizan con una lista
blanca de etiquetas. Los trámites fusionados no tienen página propia: aparecen como variantes
del trámite canónico.
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urljoin

import psycopg2
from bs4 import BeautifulSoup, Comment, NavigableString

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ingesta.tad import DATABASE_URL  # noqa: E402

DATA = RAIZ / "web" / "data"
DESCARGAS = RAIZ / "web" / "public" / "datos"

CAMPOS_TRAMITE = {
    "slug", "nombre", "descripcion", "estado", "prueba", "organismo", "categoria", "categoria_confianza",
    "destinatarios", "variantes", "canales", "requisitos", "costos", "fuentes", "descripciones",
    "reemplazado_por", "fecha_publicacion_tad", "fecha_verificacion", "norma",
}
ETIQUETAS_PERMITIDAS = {"p", "ul", "ol", "li", "strong", "b", "em", "i", "br", "a", "table", "thead", "tbody",
                        "tr", "td", "th", "h3", "h4", "h5", "blockquote"}
ENCABEZADOS = {"h1": "h3", "h2": "h3", "h6": "h5"}
PRUEBA = re.compile(r"testing de performance|prueba adm", re.IGNORECASE)
CONFIANZA = {"manual": "manual", "comercio_exterior": "alta", "organismo": "alta", "palabra_clave": "alta",
             "etiqueta": "baja", "ministerio": "baja"}
TIPO_FUENTE_PUBLICO = {"csv_tad": "tad", "api_tad": "tad", "ficha_argentina_gob_ar": "ficha", "manual": "inventario"}


def sanitizar(html, base="https://www.argentina.gob.ar"):
    """HTML de una fuente -> HTML con etiquetas de la lista blanca y links absolutos y seguros."""
    if not html:
        return None
    sopa = BeautifulSoup(html, "html.parser")
    for nodo in sopa.find_all(["script", "style", "iframe", "img", "form", "button", "svg", "noscript"]):
        nodo.decompose()
    for comentario in sopa.find_all(string=lambda s: isinstance(s, Comment)):
        comentario.extract()
    for nodo in sopa.find_all(True):
        if nodo.name in ENCABEZADOS:
            nodo.name = ENCABEZADOS[nodo.name]
        if nodo.name not in ETIQUETAS_PERMITIDAS:
            nodo.unwrap()
            continue
        href = nodo.get("href") if nodo.name == "a" else None
        nodo.attrs = {}
        if href:
            href = urljoin(base, href.strip())
            if href.startswith(("http://", "https://")):
                nodo.attrs = {"href": href, "rel": "noopener nofollow", "target": "_blank"}
            else:
                nodo.unwrap()
    for p in sopa.find_all(["p", "li"]):
        if not p.get_text(strip=True) and not p.find("br"):
            p.decompose()
    texto = re.sub(r"\s+", " ", str(sopa)).strip()
    return texto or None


def numero(v):
    if v is None:
        return None
    return int(v) if Decimal(v) == Decimal(v).to_integral_value() else float(v)


def slug_organismo(sigla, nombre, organismo_id, usados):
    import unicodedata
    base = sigla or nombre
    s = "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "organismo"
    if s in usados and usados[s] != organismo_id:
        s = f"{s}-{organismo_id}"
    usados[s] = organismo_id
    return s


def consultar(cur, sql, *params):
    cur.execute(sql, params)
    columnas = [c.name for c in cur.description]
    return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def exportar(cur):
    # Organismos ---------------------------------------------------------------
    organismos = consultar(cur, """
        SELECT o.id, o.sigla, o.nombre_oficial, o.tipo, o.padre_id, o.sucesor_id, o.vigente_desde, o.vigente_hasta,
               o.norma_creacion, o.norma_disolucion
        FROM organismo o ORDER BY o.id""")
    usados = {}
    por_id = {}
    for o in organismos:
        o["slug"] = slug_organismo(o["sigla"], o["nombre_oficial"], o["id"], usados)
        por_id[o["id"]] = o

    def raiz(organismo_id):
        vistos = set()
        while por_id[organismo_id]["padre_id"] and organismo_id not in vistos:
            vistos.add(organismo_id)
            organismo_id = por_id[organismo_id]["padre_id"]
        return organismo_id

    def org_publico(organismo_id):
        o = por_id[organismo_id]
        r = por_id[raiz(organismo_id)]
        return {"slug": o["slug"], "sigla": o["sigla"], "nombre": o["nombre_oficial"],
                "ministerio": None if r["id"] == o["id"] else {"slug": r["slug"], "sigla": r["sigla"],
                                                              "nombre": r["nombre_oficial"]}}

    # Trámites -----------------------------------------------------------------
    tramites = consultar(cur, """
        SELECT t.id, t.slug, t.nombre_ciudadano AS nombre, t.descripcion, t.estado, t.organismo_id,
               c.codigo AS categoria, c.nombre AS categoria_nombre, t.categoria_origen, t.categoria_regla,
               t.reemplazado_por_id, t.norma_base AS norma, t.fecha_ultima_verificacion,
               (SELECT (f.datos ->> 'fecha_publicacion')::date FROM fuente f
                 WHERE f.tramite_id = t.id AND f.tipo = 'csv_tad' ORDER BY f.id LIMIT 1) AS fecha_publicacion_tad,
               (SELECT f.datos ->> 'reparticion_iniciadora' FROM fuente f
                 WHERE f.tramite_id = t.id AND f.tipo = 'api_tad' LIMIT 1) AS reparticion
        FROM tramite t LEFT JOIN categoria c ON c.id = t.categoria_id
        ORDER BY t.nombre_ciudadano""")
    slug_de = {t["id"]: t["slug"] for t in tramites}

    destinatarios = defaultdict(list)
    for fila in consultar(cur, "SELECT tramite_id, tipo FROM tramite_destinatario ORDER BY tipo"):
        destinatarios[fila["tramite_id"]].append(fila["tipo"])

    autenticacion = defaultdict(list)
    for fila in consultar(cur, "SELECT canal_id, metodo, nivel_minimo FROM canal_autenticacion ORDER BY metodo"):
        autenticacion[fila["canal_id"]].append(fila["metodo"])
    canales = defaultdict(list)
    for fila in consultar(cur, """
            SELECT c.id, c.tramite_id, c.modalidad, p.codigo AS plataforma, p.nombre AS plataforma_nombre,
                   c.url_inicio, c.requiere_turno, c.detalle
            FROM canal c LEFT JOIN plataforma p ON p.id = c.plataforma_id
            WHERE c.activo ORDER BY c.id"""):
        canales[fila["tramite_id"]].append({
            "modalidad": fila["modalidad"], "plataforma": fila["plataforma"],
            "plataforma_nombre": fila["plataforma_nombre"], "url": fila["url_inicio"],
            "requiere_turno": fila["requiere_turno"], "detalle": fila["detalle"],
            "autenticacion": autenticacion.get(fila["id"], []),
        })

    requisitos = defaultdict(list)
    for fila in consultar(cur, """
            SELECT r.tramite_id, r.descripcion, r.tipo, r.seccion, r.obligatorio, r.tramite_previo_id, f.tipo AS fuente
            FROM requisito r LEFT JOIN fuente f ON f.id = r.fuente_id
            ORDER BY r.fuente_id NULLS FIRST, r.orden"""):
        requisitos[fila["tramite_id"]].append({
            "descripcion": fila["descripcion"], "tipo": fila["tipo"], "seccion": fila["seccion"],
            "obligatorio": fila["obligatorio"], "fuente": TIPO_FUENTE_PUBLICO.get(fila["fuente"], "manual"),
            "previo": slug_de.get(fila["tramite_previo_id"]),
        })

    costos = defaultdict(list)
    for fila in consultar(cur, """
            SELECT c.tramite_id, c.concepto, c.gratuito, c.monto_min, c.monto_max, c.unidad, c.norma, c.detalle,
                   c.vigente_desde, v.nombre AS variante, f.tipo AS fuente
            FROM costo c LEFT JOIN tramite_variante v ON v.id = c.variante_id LEFT JOIN fuente f ON f.id = c.fuente_id
            WHERE c.vigente_hasta IS NULL ORDER BY c.id"""):
        costos[fila["tramite_id"]].append({
            "concepto": fila["concepto"], "gratuito": fila["gratuito"], "monto_min": numero(fila["monto_min"]),
            "monto_max": numero(fila["monto_max"]), "unidad": fila["unidad"], "norma": fila["norma"],
            "detalle": fila["detalle"], "variante": fila["variante"],
            "vigente_desde": fila["vigente_desde"].isoformat() if fila["vigente_desde"] else None,
            "fuente": TIPO_FUENTE_PUBLICO.get(fila["fuente"], "manual"),
        })

    variantes = defaultdict(list)
    for fila in consultar(cur, """
            SELECT v.tramite_id, v.nombre, v.tramite_origen_id,
                   (SELECT f.id_externo FROM fuente f WHERE f.tramite_id = v.tramite_origen_id AND f.tipo = 'csv_tad'
                     LIMIT 1) AS id_tad
            FROM tramite_variante v ORDER BY v.id"""):
        variantes[fila["tramite_id"]].append({"nombre": fila["nombre"], "id_tad": fila["id_tad"]})
        if fila["tramite_origen_id"] and fila["tramite_origen_id"] != fila["tramite_id"]:
            # Requisitos y costos del trámite fusionado se muestran en el canónico, rotulados con la variante.
            for r in requisitos.get(fila["tramite_origen_id"], []):
                requisitos[fila["tramite_id"]].append({**r, "seccion": f"{fila['nombre']}: {r['seccion'] or ''}".strip(": ")})
            for c in costos.get(fila["tramite_origen_id"], []):
                costos[fila["tramite_id"]].append({**c, "variante": c["variante"] or fila["nombre"]})
            for c in canales.get(fila["tramite_origen_id"], []):
                canales[fila["tramite_id"]].append({**c, "detalle": c["detalle"] or fila["nombre"]})

    fuentes = defaultdict(list)
    descripciones = defaultdict(dict)
    for fila in consultar(cur, """
            SELECT f.tramite_id, f.tipo, f.id_externo, f.url, f.fecha_captura, f.activo,
                   f.datos ->> 'descripcion_html' AS html_tad, f.datos -> 'secciones' AS secciones,
                   f.datos ->> 'actualizado' AS actualizado
            FROM fuente f WHERE f.tramite_id IS NOT NULL ORDER BY f.id"""):
        tipo = fila["tipo"]
        if tipo == "csv_tad":
            fuentes[fila["tramite_id"]].append({
                "tipo": "tad", "id": fila["id_externo"], "activo": fila["activo"],
                "url": f"https://tramitesadistancia.gob.ar/tramitesadistancia/detalle-tipo?id={fila['id_externo']}",
                "capturado": fila["fecha_captura"].date().isoformat()})
        elif tipo == "api_tad" and fila["html_tad"]:
            descripciones[fila["tramite_id"]]["tad"] = sanitizar(fila["html_tad"], "https://tramitesadistancia.gob.ar")
        elif tipo == "ficha_argentina_gob_ar":
            fuentes[fila["tramite_id"]].append({
                "tipo": "ficha", "id": fila["id_externo"], "activo": fila["activo"], "url": fila["url"],
                "capturado": fila["fecha_captura"].date().isoformat(), "actualizado": fila["actualizado"]})
            secciones = fila["secciones"] or {}
            descripciones[fila["tramite_id"]]["ficha"] = {
                k: sanitizar(secciones.get(k)) for k in ("dirigido", "necesito", "como", "costo", "tiempo", "vigencia")
                if secciones.get(k)}
        elif tipo == "manual":
            fuentes[fila["tramite_id"]].append({
                "tipo": "inventario", "id": fila["id_externo"], "activo": fila["activo"], "url": fila["url"],
                "capturado": fila["fecha_captura"].date().isoformat()})

    salida = []
    for t in tramites:
        if t["estado"] == "fusionado":
            continue
        tid = t["id"]
        registro = {
            "slug": t["slug"], "nombre": t["nombre"], "descripcion": t["descripcion"], "estado": t["estado"],
            # Por nombre: la repartición TESTSADE también inicia algún trámite real (p. ej. TAD 4598).
            "prueba": bool(PRUEBA.search(t["nombre"] or "")),
            "organismo": org_publico(t["organismo_id"]),
            "categoria": {"codigo": t["categoria"], "nombre": t["categoria_nombre"]} if t["categoria"] else None,
            "categoria_confianza": "manual" if t["categoria_origen"] == "manual" else CONFIANZA.get(t["categoria_regla"]),
            "destinatarios": destinatarios.get(tid, []),
            "variantes": variantes.get(tid, []),
            "canales": canales.get(tid, []),
            "requisitos": requisitos.get(tid, []),
            "costos": costos.get(tid, []),
            "fuentes": fuentes.get(tid, []),
            "descripciones": descripciones.get(tid, {}),
            "reemplazado_por": slug_de.get(t["reemplazado_por_id"]),
            "fecha_publicacion_tad": t["fecha_publicacion_tad"].isoformat() if t["fecha_publicacion_tad"] else None,
            "fecha_verificacion": t["fecha_ultima_verificacion"].isoformat() if t["fecha_ultima_verificacion"] else None,
            "norma": t["norma"],
        }
        assert set(registro) <= CAMPOS_TRAMITE, set(registro) - CAMPOS_TRAMITE
        salida.append(registro)
    return salida, organismos, por_id, raiz


def costo_resumen(t):
    """'gratuito' | 'arancelado' | None (sin dato), mirando todas las fuentes."""
    if any(not c["gratuito"] for c in t["costos"]):
        return "arancelado"
    if t["costos"]:
        return "gratuito"
    return None


def agregar(tramites, organismos, por_id, raiz, cur):
    contables = [t for t in tramites if t["estado"] == "vigente" and not t["prueba"]]
    total = len(contables)

    def pct(k):
        return round(100 * k / total, 1) if total else 0

    online = sum(any(c["modalidad"] in ("online", "mixta") for c in t["canales"]) for t in contables)
    presencial = sum(any(c["modalidad"] in ("presencial", "mixta", "consular") for c in t["canales"]) for t in contables)
    costo = Counter(costo_resumen(t) for t in contables)
    con_requisitos = sum(bool(t["requisitos"]) for t in contables)
    con_categoria = sum(bool(t["categoria"]) for t in contables)
    con_destinatario = sum(bool(t["destinatarios"]) for t in contables)
    por_fuente = Counter(f["tipo"] for t in contables for f in {f["tipo"]: f for f in t["fuentes"]}.values())
    solo_publico = [t for t in contables if t["destinatarios"] != ["organismo_publico"]]

    por_categoria = Counter((t["categoria"] or {}).get("codigo") for t in contables)
    nombres_categoria = {t["categoria"]["codigo"]: t["categoria"]["nombre"] for t in contables if t["categoria"]}
    por_organismo = Counter(t["organismo"]["slug"] for t in contables)
    por_ministerio = Counter((t["organismo"]["ministerio"] or t["organismo"])["slug"] for t in contables)
    org_por_slug = {o["slug"]: o for o in organismos}

    plataformas = Counter()
    for t in contables:
        for p in {c["plataforma_nombre"] for c in t["canales"] if c["plataforma_nombre"]}:
            plataformas[p] += 1
    autenticacion = Counter()
    for t in contables:
        for m in {m for c in t["canales"] for m in c["autenticacion"]}:
            autenticacion[m] += 1
    destinatarios = Counter(d for t in contables for d in t["destinatarios"])
    anios = Counter(t["fecha_publicacion_tad"][:4] for t in contables if t["fecha_publicacion_tad"])

    # Costos: cuánto subestima el CSV de TAD (marca "no arancelado" pero la descripción o la ficha dan un monto).
    subestimados = sum(
        1 for t in contables
        if any(c["concepto"] == "arancel TAD" and c["gratuito"] for c in t["costos"])
        and any(c["concepto"] != "arancel TAD" and not c["gratuito"] and c["monto_max"] for c in t["costos"]))
    discrepancias = []
    for t in contables:
        csv_ = [c for c in t["costos"] if c["concepto"] == "arancel TAD" and not c["gratuito"] and c["monto_max"]]
        otros = [c for c in t["costos"] if c["concepto"] != "arancel TAD" and not c["gratuito"] and c["monto_max"]
                 and c["unidad"] == "ARS" and not c["variante"]]
        for a in csv_:
            for b in otros:
                if not (b["monto_min"] <= a["monto_max"] and b["monto_max"] >= a["monto_min"]):
                    discrepancias.append({"slug": t["slug"], "nombre": t["nombre"], "csv": a["monto_max"],
                                          "otra_fuente": b["monto_max"], "fuente": b["fuente"]})
    montos = sorted(max(c["monto_max"] for c in t["costos"] if not c["gratuito"] and c["monto_max"] and c["unidad"] == "ARS")
                    for t in contables if any(not c["gratuito"] and c["monto_max"] and c["unidad"] == "ARS" for c in t["costos"]))
    tramos = [(0, 10_000, "Hasta $10.000"), (10_000, 50_000, "$10.000 – $50.000"), (50_000, 200_000, "$50.000 – $200.000"),
              (200_000, 1_000_000, "$200.000 – $1 millón"), (1_000_000, float("inf"), "Más de $1 millón")]
    distribucion = [{"tramo": nombre, "tramites": sum(1 for m in montos if a < m <= b or (a == 0 and m == 0))}
                    for a, b, nombre in tramos]

    # Requisitos más pedidos, agrupados por documento.
    documentos = [
        ("DNI", r"\bDNI\b|DOCUMENTO NACIONAL DE IDENTIDAD"), ("CUIT / CUIL", r"\bCUI[TL]\b"),
        ("Clave fiscal", r"CLAVE FISCAL"), ("Estatuto o contrato social", r"ESTATUTO|CONTRATO SOCIAL"),
        ("Poder o acreditación de representación", r"\bPODER\b|REPRESENTACI|APODERAD"),
        ("Estados contables o balance", r"ESTADOS? CONTABLES?|\bBALANCE"),
        ("Nota o formulario de solicitud", r"\bNOTA\b|FORMULARIO"),
        ("Comprobante de pago", r"COMPROBANTE DE PAGO|\bVEP\b|BOLETA DE PAGO"),
        ("Título o certificado profesional", r"\bTITULO\b|MATRICULA"),
        ("Declaración jurada", r"DECLARACION(ES)? JURADA"), ("Planos", r"\bPLANOS?\b"),
        ("Habilitación municipal o provincial", r"HABILITACION (MUNICIPAL|PROVINCIAL)"),
        ("Constancia de domicilio", r"DOMICILIO"), ("Certificado de antecedentes", r"ANTECEDENTES"),
    ]
    from ingesta.normalizar import clave
    requisitos_top = Counter()
    for t in contables:
        textos = [clave(r["descripcion"]) for r in t["requisitos"]]
        for nombre, patron in documentos:
            if any(re.search(patron, x) for x in textos):
                requisitos_top[nombre] += 1

    cambios = []
    for o in organismos:
        if o["sucesor_id"]:
            s = por_id[o["sucesor_id"]]
            cambios.append({"anterior": o["nombre_oficial"], "anterior_sigla": o["sigla"], "sucesor": s["nombre_oficial"],
                            "sucesor_sigla": s["sigla"], "sucesor_slug": s["slug"],
                            "fecha": o["vigente_hasta"].isoformat() if o["vigente_hasta"] else None,
                            "norma": o["norma_disolucion"] or s["norma_creacion"],
                            "tramites": por_organismo.get(s["slug"], 0)})

    return {
        "totales": {
            "tramites": total, "organismos": len(por_organismo), "ministerios": len(por_ministerio),
            "online_pct": pct(online), "presencial_pct": pct(presencial),
            "arancelados_pct": pct(costo["arancelado"]), "gratuitos_pct": pct(costo["gratuito"]),
            "costo_sin_dato_pct": pct(costo[None]), "con_requisitos_pct": pct(con_requisitos),
            "con_categoria_pct": pct(con_categoria), "con_destinatario_pct": pct(con_destinatario),
            "para_ciudadanos_y_empresas": len(solo_publico),
            "variantes": sum(len(t["variantes"]) for t in contables),
            "bajas": sum(t["estado"] == "baja" for t in tramites),
            "prueba": sum(t["prueba"] for t in tramites),
            "por_fuente": dict(por_fuente),
        },
        "por_categoria": [{"codigo": c or "sin_categoria", "nombre": nombres_categoria.get(c, "Sin categoría"), "tramites": k}
                          for c, k in por_categoria.most_common()],
        "por_ministerio": [{"slug": s, "sigla": org_por_slug[s]["sigla"], "nombre": org_por_slug[s]["nombre_oficial"],
                            "tramites": k} for s, k in por_ministerio.most_common()],
        "por_organismo": [{"slug": s, "sigla": org_por_slug[s]["sigla"], "nombre": org_por_slug[s]["nombre_oficial"],
                           "tramites": k} for s, k in por_organismo.most_common(40)],
        "por_plataforma": [{"plataforma": p, "tramites": k} for p, k in plataformas.most_common()],
        "autenticacion": [{"metodo": m, "tramites": k} for m, k in autenticacion.most_common()],
        "por_destinatario": [{"tipo": d, "tramites": k} for d, k in destinatarios.most_common()],
        "por_anio_publicacion_tad": [{"anio": a, "tramites": anios[a]} for a in sorted(anios)],
        "costos": {"gratuitos": costo["gratuito"], "arancelados": costo["arancelado"], "sin_dato": costo[None],
                   "subestimados_csv_tad": subestimados, "distribucion": distribucion,
                   "mediana": montos[len(montos) // 2] if montos else None, "discrepancias": discrepancias[:50]},
        "requisitos_top": [{"documento": d, "tramites": k} for d, k in requisitos_top.most_common()],
        "cambios_institucionales": cambios,
    }


def escribir_json(ruta, datos, compacto=True):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":") if compacto else None,
                       indent=None if compacto else 1, default=str)
    ruta.write_text(texto, encoding="utf-8")
    return len(texto.encode("utf-8"))


def escribir_csv(ruta, columnas, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        w.writerows(filas)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn, conn.cursor() as cur:
            tramites, organismos, por_id, raiz = exportar(cur)
            agregados = agregar(tramites, organismos, por_id, raiz, cur)
            cur.execute("SELECT max((datos ->> 'fecha_publicacion')::date) FROM fuente WHERE tipo = 'csv_tad'")
            max_publicacion = cur.fetchone()[0]
            cur.execute("""SELECT fuente_tipo, max(finalizada_en)::date FROM ingesta_corrida
                           WHERE estado = 'ok' GROUP BY 1""")
            corridas = {k: v.isoformat() for k, v in cur.fetchall() if v}
    finally:
        conn.close()

    por_organismo = Counter(t["organismo"]["slug"] for t in tramites if t["estado"] == "vigente" and not t["prueba"])
    usados = {o["slug"] for o in organismos if por_organismo.get(o["slug"])}
    # Incluir ancestros y sucesores de organismos con trámites (para la jerarquía y los cambios institucionales).
    ids_usados = {o["id"] for o in organismos if o["slug"] in usados}
    for o in list(organismos):
        if o["id"] in ids_usados:
            p = o["padre_id"]
            while p:
                ids_usados.add(p)
                p = por_id[p]["padre_id"]
        if o["sucesor_id"] and o["sucesor_id"] in ids_usados:
            ids_usados.add(o["id"])
    organismos_publicos = [{
        "slug": o["slug"], "sigla": o["sigla"], "nombre": o["nombre_oficial"], "tipo": o["tipo"],
        "padre": por_id[o["padre_id"]]["slug"] if o["padre_id"] else None,
        "sucesor": por_id[o["sucesor_id"]]["slug"] if o["sucesor_id"] else None,
        "vigente_hasta": o["vigente_hasta"].isoformat() if o["vigente_hasta"] else None,
        "norma_creacion": o["norma_creacion"], "norma_disolucion": o["norma_disolucion"],
        "tramites": por_organismo.get(o["slug"], 0),
    } for o in organismos if o["id"] in ids_usados]

    indice = [{
        "s": t["slug"], "n": t["nombre"], "o": t["organismo"]["sigla"] or t["organismo"]["nombre"],
        "os": t["organismo"]["slug"], "c": (t["categoria"] or {}).get("codigo"), "d": t["destinatarios"],
        "m": sorted({c["modalidad"] for c in t["canales"]}), "p": sorted({c["plataforma"] for c in t["canales"] if c["plataforma"]}),
        "g": costo_resumen(t), "e": t["estado"], "x": t["prueba"],
    } for t in tramites]

    meta = {"fecha_corte": date.today().isoformat(), "max_fecha_publicacion_tad": max_publicacion.isoformat()
            if max_publicacion else None, "ultimas_corridas": corridas}

    tamanos = {
        "tramites.json": escribir_json(DATA / "tramites.json", tramites),
        # El índice lo baja el buscador del lado del cliente: va a public/ para no inflar el HTML.
        "indice-busqueda.json": escribir_json(RAIZ / "web" / "public" / "indice-busqueda.json", indice),
        "organismos.json": escribir_json(DATA / "organismos.json", organismos_publicos, compacto=False),
        "agregados.json": escribir_json(DATA / "agregados.json", agregados, compacto=False),
        "meta.json": escribir_json(DATA / "meta.json", meta, compacto=False),
    }

    escribir_csv(DESCARGAS / "tramites.csv",
                 ["slug", "nombre", "estado", "organismo", "ministerio", "categoria", "destinatarios", "modalidades",
                  "plataformas", "costo", "url_tad", "url_ficha"],
                 [[t["slug"], t["nombre"], t["estado"], t["organismo"]["nombre"],
                   (t["organismo"]["ministerio"] or t["organismo"])["nombre"], (t["categoria"] or {}).get("nombre"),
                   ";".join(t["destinatarios"]), ";".join(sorted({c["modalidad"] for c in t["canales"]})),
                   ";".join(sorted({c["plataforma_nombre"] for c in t["canales"] if c["plataforma_nombre"]})),
                   costo_resumen(t) or "",
                   next((f["url"] for f in t["fuentes"] if f["tipo"] == "tad"), ""),
                   next((f["url"] for f in t["fuentes"] if f["tipo"] == "ficha"), "")]
                  for t in tramites if not t["prueba"]])
    escribir_csv(DESCARGAS / "requisitos.csv", ["tramite", "requisito", "tipo", "seccion", "obligatorio", "fuente"],
                 [[t["slug"], r["descripcion"], r["tipo"], r["seccion"] or "", r["obligatorio"], r["fuente"]]
                  for t in tramites if not t["prueba"] for r in t["requisitos"]])
    escribir_csv(DESCARGAS / "costos.csv",
                 ["tramite", "concepto", "variante", "gratuito", "monto_min", "monto_max", "unidad", "norma", "fuente", "detalle"],
                 [[t["slug"], c["concepto"], c["variante"] or "", c["gratuito"], c["monto_min"] or "", c["monto_max"] or "",
                   c["unidad"], c["norma"] or "", c["fuente"], c["detalle"] or ""]
                  for t in tramites if not t["prueba"] for c in t["costos"]])
    escribir_csv(DESCARGAS / "organismos.csv", ["slug", "sigla", "nombre", "tipo", "depende_de", "sucesor", "tramites"],
                 [[o["slug"], o["sigla"] or "", o["nombre"], o["tipo"] or "", o["padre"] or "", o["sucesor"] or "", o["tramites"]]
                  for o in organismos_publicos])
    escribir_json(DESCARGAS / "tramites.json", [t for t in tramites if not t["prueba"]])

    print(f"Exportados {len(tramites)} trámites ({agregados['totales']['tramites']} contables), "
          f"{len(organismos_publicos)} organismos.")
    for archivo, bytes_ in tamanos.items():
        print(f"  {archivo}: {bytes_ / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
