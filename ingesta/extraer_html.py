"""Extracción de requisitos y costos de la descripción HTML de un trámite TAD.

Funciones puras (sin base de datos); se testean en tests/test_extraer_html.py.

Las descripciones las escribe cada organismo sin plantilla común, así que la
extracción es heurística y conservadora: se queda con lo que aparece bajo un
título de requisitos o documentación, y con montos en contexto de costo.
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Comment, NavigableString

from ingesta import normalizar as n

# Títulos (normalizados con n.clave) que abren una sección de requisitos.
TITULO_REQUISITOS = re.compile(
    r"REQUISIT|DOCUMENTACI|QUE NECESITO|ADJUNTAR|SE LE REQUERIRA|"
    r"DEBERA (PRESENTAR|SUBIR|ACOMPANAR)|SE DEBE(N|RA)? (INCLUIR|PRESENTAR|SUBIR|ACOMPANAR)|"
    r"PARA LLEVAR ADELANTE EL TRAMITE|PARA INICIAR (EL TRAMITE|LA INSCRIPCION)|RESULTA NECESARI|DENTRO DEL SOBRE"
)
# Secciones de pasos u otra información: cierran una sección de requisitos.
TITULO_OTRA_SECCION = re.compile(
    r"SIGUIENTES PASOS|COMO HAGO|COMO SE HACE|COMO SE REALIZA|COSTO|CUANTO|ARANCEL|A QUIEN|QUIEN PUEDE|"
    r"IMPORTANTE|ACLARACION|OBSERVACION|^NOTA|CONSULTA|DONDE|VIGENCIA|TIEMPO|PLAZO|EN QUE CONSISTE|DESCRIPCION|"
    r"RESOLUCION|NORMATIVA|MARCO NORMATIVO"
)
TITULO_COSTO = re.compile(r"COSTO|CUANTO (VALE|CUESTA|SALE)|ARANCEL|TASA|VALOR DEL TRAMITE")
# Ítems que son pasos de la plataforma, no requisitos.
PASO_PLATAFORMA = re.compile(
    r"^(COMPLETAR|INGRESAR|INGRESA|VERIFICAR|CONFIRMAR|SELECCIONAR|HACER CLIC|PRESIONAR|INICIAR|ACCEDER|"
    r"CARGAR LOS DATOS|DIRIGIRSE|ELEGIR|BUSCAR)\b"
)
VINETA = re.compile(r"^\s*(?:[•·▪●○◦\-–*]|\(?[a-zA-Z]\)|\(?\d{1,2}[).\-]|[ivx]{1,4}\))\s+")

PALABRAS_COSTO = re.compile(r"ARANCEL|COSTO|VALOR|TASA|ABONA|CUESTA|VALE |PAGO|PAGAR|CANON|DERECHO DE")
NO_ES_COSTO = re.compile(
    r"SUBSIDI|CREDITO|PRESTAMO|FINANCIA|MONTO MAXIMO|MONTO MINIMO|TOPE|SUPERE|INGRESO|SALARIO|FACTURACION|"
    r"BENEFICIO|REEMBOLSABLE|PREMIO|MILLON|PATRIMONIO|CAPITAL SOCIAL|MULTA"
)
MONTO = re.compile(
    r"(?P<moneda>U\$S|US\$|USD|\$)\s?(?P<valor>\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
)
GRATUITO = re.compile(r"ES GRATUITO|SIN COSTO|NO TIENE COSTO|NO POSEE COSTO|NO TIENE ARANCEL|NO ABONA|GRATUITA")
# Frase (no título) que anuncia una lista de documentos: "...los documentos detallados en la Resolución...".
INTRO_DOCUMENTOS = re.compile(
    r"SIGUIENTE DOCUMENTACION|SIGUIENTES DOCUMENTOS|DOCUMENTOS DETALLADOS|DOCUMENTACION QUE SE DETALLA|"
    r"DOCUMENTACION REQUERIDA|ADJUNTAR LO SIGUIENTE|SIGUIENTES REQUISITOS"
)
# Párrafos sin viñeta dentro de una sección de requisitos que son notas, no requisitos.
NOTA = re.compile(
    r"^(PARA MAS INFORMACION|PARA ASESORAMIENTO|POR CONSULTAS|CONSULTAS|RECORDA|RECUERDE|TENER EN CUENTA|TENGA EN CUENTA|"
    r"IMPORTANTE|NOTA|ACLARACION|OBSERVACION|SE RECOMIENDA|LOS MODELOS|EL MODELO|DESCARGA|QUEDAN EXCLUIDOS|"
    r"ESTE TRAMITE|EL TRAMITE|N[OU]? ?\d|RESOL|DISPOSICION|DECRETO|LEY )"
)
LARGO_MAXIMO_PARRAFO = 500

LARGO_MAXIMO = 2000


@dataclass
class Requisito:
    descripcion: str
    tipo: str
    seccion: str
    obligatorio: bool


@dataclass
class Costo:
    gratuito: bool
    unidad: str
    monto_min: object
    monto_max: object
    detalle: str


# Linealización del HTML ----------------------------------------------------

BLOQUES = ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "tr", "td", "li",
           "blockquote", "section", "body", "html"]
ENCABEZADOS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _es_bloque(nodo):
    return not isinstance(nodo, NavigableString) and (nodo.name in BLOQUES or nodo.find(BLOQUES) is not None)


def _texto(nodos):
    """Texto de nodos en línea, partido en líneas solo por <br> (ya convertidos en '\\n')."""
    texto = "".join(str(x) if isinstance(x, NavigableString) else x.get_text(" ") for x in nodos)
    return [l for l in (n.texto(x) for x in texto.split("\n")) if l]


def _solo_negrita(nodos):
    hijos = [c for c in nodos if not (isinstance(c, NavigableString) and not c.strip())]
    return bool(hijos) and all(getattr(c, "name", None) in ("strong", "b") for c in hijos)


def lineas(html):
    """HTML -> [(tipo, texto, etiqueta_padre)] con tipo 'titulo', 'item' o 'texto'.

    etiqueta_padre es el texto del <li> que contiene a una sublista ("Subir la
    siguiente documentación:"), para los ítems anidados.
    """
    sopa = BeautifulSoup(html or "", "html.parser")
    for comentario in sopa.find_all(string=lambda s: isinstance(s, Comment)):
        comentario.extract()
    # Los saltos de línea del código fuente no separan nada; solo <br> y los bloques.
    for cadena in sopa.find_all(string=True):
        cadena.replace_with(re.sub(r"\s+", " ", str(cadena)))
    for br in sopa.find_all("br"):
        br.replace_with("\n")
    resultado = []

    def lista(nodo, padre):
        for li in nodo.find_all("li", recursive=False):
            sublistas = [s.extract() for s in li.find_all(["ul", "ol"], recursive=False)]
            propio = " ".join(_texto(li.contents))
            if propio:
                resultado.append(("item", propio, padre))
            for s in sublistas:
                lista(s, propio or padre)

    def recorrer(nodo):
        en_linea = []

        def vaciar():
            partes = _texto(en_linea)
            negrita = len(partes) == 1 and _solo_negrita(en_linea)
            for l in partes:
                resultado.append(("titulo" if negrita or es_titulo(l) else "texto", l, None))
            en_linea.clear()

        for hijo in nodo.children:
            if not _es_bloque(hijo):
                en_linea.append(hijo)
                continue
            vaciar()
            if hijo.name in ("ul", "ol"):
                lista(hijo, None)
            elif hijo.name in ENCABEZADOS:
                texto = " ".join(_texto(hijo.contents))
                if texto:
                    resultado.append(("titulo", texto, None))
            else:
                recorrer(hijo)
        vaciar()

    recorrer(sopa)
    return resultado


def es_titulo(linea):
    if VINETA.match(linea):
        return False
    return (linea.endswith(":") and len(linea) <= 150) or (linea.startswith("¿") and linea.endswith("?"))


# Requisitos ----------------------------------------------------------------

def tipo_requisito(texto):
    k = n.clave(texto)
    if re.search(r"COMPROBANTE DE PAGO|PAGO DE (LA |EL )?(ARANCEL|TASA)|ABONAR|TASA RETRIBUTIVA|BOLETA DE PAGO", k):
        return "pago_previo"
    if re.match(r"(SER|TENER|ESTAR|CONTAR CON|NO TENER|NO ESTAR|POSEER|HABER|ACREDITAR SER)\b", k):
        return "condicion"
    return "documento"


def requisitos(html):
    resultado = []
    seccion, obligatorio, en_requisitos = None, True, False

    def agregar(texto, seccion_item, obligatorio_item):
        texto = VINETA.sub("", texto).strip()
        k = n.clave(texto)
        if len(k) < 4 or PASO_PLATAFORMA.match(k) or texto.endswith(":"):
            return
        opcional = "OPCIONAL" in k and "NO OPCIONAL" not in k
        resultado.append(Requisito(texto[:LARGO_MAXIMO], tipo_requisito(texto), seccion_item,
                                   obligatorio_item and not opcional))

    for tipo, texto, padre in lineas(html):
        k = n.clave(texto)
        if tipo == "titulo":
            if TITULO_REQUISITOS.search(k) and not TITULO_OTRA_SECCION.search(k):
                en_requisitos, seccion = True, texto.rstrip(":").strip()
                obligatorio = "OPCIONAL" not in k
            elif en_requisitos and texto.endswith(":") and not TITULO_OTRA_SECCION.search(k):
                seccion = texto.rstrip(":").strip()  # subsección: "Personas jurídicas:"
            else:
                en_requisitos = False
            continue
        if tipo == "item":
            # Un <li> "Subir la siguiente documentación:" abre requisitos para sus ítems anidados.
            if padre and TITULO_REQUISITOS.search(n.clave(padre)):
                agregar(texto, padre.rstrip(":").strip(), "OPCIONAL" not in n.clave(padre))
            elif en_requisitos:
                agregar(texto, seccion, obligatorio)
            continue
        if not en_requisitos:
            # Una frase que anuncia documentos abre la sección aunque no sea un título.
            if INTRO_DOCUMENTOS.search(k) and len(texto) <= LARGO_MAXIMO_PARRAFO:
                en_requisitos, seccion, obligatorio = True, texto.rstrip(":.").strip(), True
            continue
        if VINETA.match(texto):
            agregar(texto, seccion, obligatorio)
        elif (len(texto) <= LARGO_MAXIMO_PARRAFO and not NOTA.match(k) and "HTTP" not in k
              and not GRATUITO.search(k) and not MONTO.search(texto)):
            agregar(texto, seccion, obligatorio)
    return resultado


# Costos --------------------------------------------------------------------

def oraciones(texto):
    return [o for o in (n.texto(x) for x in re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚ¿(])|\n", texto)) if o]


def costos(html):
    """Costos mencionados en la descripción: una fila por unidad (ARS, USD), o una gratuita."""
    contexto, en_costo = [], False
    for tipo, texto, _ in lineas(html):
        k = n.clave(texto)
        if tipo == "titulo":
            en_costo = bool(TITULO_COSTO.search(k))
            # El título puede traer el monto: "Costo: $ 45.000"
            if en_costo and MONTO.search(texto):
                contexto.append((texto, True))
            continue
        for o in oraciones(texto):
            contexto.append((o, en_costo))

    por_unidad, gratuito, detalles = {}, False, []
    for oracion, en_seccion in contexto:
        k = n.clave(oracion)
        montos = list(MONTO.finditer(oracion))
        if not montos:
            if GRATUITO.search(k) and (en_seccion or "TRAMITE" in k):
                gratuito = True
            continue
        if NO_ES_COSTO.search(k) or not (en_seccion or PALABRAS_COSTO.search(k)):
            continue
        detalles.append(oracion)
        for m in montos:
            unidad = "ARS" if m["moneda"] == "$" else "USD"
            try:
                valor = n.monto(m["valor"])
            except ValueError:
                continue
            if valor:
                por_unidad.setdefault(unidad, []).append(valor)

    detalle = " ".join(dict.fromkeys(detalles))[:LARGO_MAXIMO] or None
    if por_unidad:
        return [Costo(False, u, min(v), max(v), detalle) for u, v in sorted(por_unidad.items())]
    if gratuito:
        return [Costo(True, "ARS", None, None, None)]
    return []
