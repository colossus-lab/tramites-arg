"""Lectura y normalización de los CSV de TAD (datos.gob.ar, dataset JGM 26).

Funciones puras, sin base de datos: se testean en tests/test_normalizar.py.
"""

import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal

# Nombre canónico de cada columna -> nombres alternativos aceptados en el CSV.
COLUMNAS = {
    "ID_TRAMITE": ("ID_TRAMITE", "ID", "ID_TIPO_TRAMITE"),
    "NOMBRE_TRAMITE": ("NOMBRE_TRAMITE", "NOMBRE", "TRAMITE"),
    "ORGANO_RECTOR": ("ORGANO_RECTOR", "ORGANISMO", "REPARTICION"),
    "FECHA_PUBLICACION_PROD": ("FECHA_PUBLICACION_PROD", "FECHA_PUBLICACION"),
    "MARCA_ARANCELADO": ("MARCA_ARANCELADO", "ARANCELADO"),
    "LINK_DE_ACCESO": ("LINK_DE_ACCESO", "LINK", "URL"),
    "VALIDADOR_IDENTIDAD": ("VALIDADOR_IDENTIDAD", "VALIDADORES"),
    "PAGO_MINIMO": ("PAGO_MINIMO",),
    "PAGO_MAXIMO": ("PAGO_MAXIMO",),
    "PAGO_PROMEDIO": ("PAGO_PROMEDIO",),
}

# Valores de VALIDADOR_IDENTIDAD -> canal_autenticacion.metodo (o varios métodos)
METODOS_AUTENTICACION = {
    # El detalle de TAD muestra dos ingresos para estos trámites: "NIC No Residentes" y "ARCA".
    "NIC AFIP": ("nic_no_residente", "clave_fiscal"),
    "MI ARGENTINA": "mi_argentina",
    "MIARGENTINA": "mi_argentina",
    "AFIP": "clave_fiscal",
    "ARCA": "clave_fiscal",
    "CLAVE FISCAL": "clave_fiscal",
    "ANSES": "css_anses",
    "CLAVE DE LA SEGURIDAD SOCIAL": "css_anses",
    "DNI": "dni_tramite",
    "RENAPER": "dni_tramite",
    "NIC": "nic_no_residente",
    "NO RESIDENTES": "nic_no_residente",
    "FIRMA DIGITAL": "firma_digital",
}

_VERDADEROS = {"SI", "S", "TRUE", "VERDADERO", "1", "X", "ARANCELADO"}
_FALSOS = {"NO", "N", "FALSE", "FALSO", "0", "NO ARANCELADO"}
_FORMATOS_FECHA = ("%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y", "%Y/%m/%d")


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def clave(s):
    """'Fecha publicación prod' -> 'FECHA PUBLICACION PROD' (mayúsculas, sin tildes ni puntuación)."""
    return re.sub(r"[^A-Z0-9]+", " ", sin_tildes(s).upper()).strip()


def clave_columna(nombre):
    return clave(nombre).replace(" ", "_")


def texto(v):
    v = re.sub(r"\s+", " ", v or "").strip()
    return v or None


def entero(v):
    v = texto(v)
    if v is None:
        return None
    if not re.fullmatch(r"\d+(\.0+)?", v):
        raise ValueError(f"no es un entero: {v!r}")
    return int(v.split(".")[0])


def booleano(v):
    k = clave(v or "")
    if not k:
        return None
    if k in _VERDADEROS:
        return True
    if k in _FALSOS:
        return False
    raise ValueError(f"valor booleano desconocido: {v!r}")


def fecha(v):
    v = texto(v)
    if v is None:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(v, formato).date()
        except ValueError:
            continue
    raise ValueError(f"fecha no reconocida: {v!r}")


def monto(v):
    """Montos con separadores inconsistentes: '1.795.500.00', '1.234,56', '1500', '$ 2.400'.

    El último separador es decimal si le siguen 1 o 2 dígitos, o si se mezclan
    puntos y comas. Si le siguen exactamente 3 dígitos se lo toma como miles.
    """
    s = re.sub(r"\s|\$|ARS", "", v or "", flags=re.IGNORECASE)
    if s in ("", "-", "--"):
        return None
    if not re.fullmatch(r"\d[\d.,]*", s):
        raise ValueError(f"monto no reconocido: {v!r}")
    ultimo = max(s.rfind("."), s.rfind(","))
    if ultimo == -1:
        return Decimal(s)
    sep, cabeza, cola = s[ultimo], s[:ultimo], s[ultimo + 1:]
    otro = "," if sep == "." else "."
    if len(cola) == 3 and otro not in cabeza:
        entera, decimales = s, ""
    else:
        entera, decimales = cabeza, cola
    entera = re.sub(r"[.,]", "", entera) or "0"
    return Decimal(f"{entera}.{decimales or '0'}")


def metodos(original):
    """'NIC-AFIP' -> ('nic_no_residente', 'clave_fiscal'); un valor desconocido -> ('otro',)."""
    metodo = METODOS_AUTENTICACION.get(clave(original), "otro")
    return metodo if isinstance(metodo, tuple) else (metodo,)


def validadores(v):
    """'DNI,Mi argentina,ANSES,AFIP' -> [('dni_tramite', 'DNI'), ('mi_argentina', 'Mi argentina'), ...]."""
    resultado = []
    for parte in re.split(r"[,;|/]", v or ""):
        original = texto(parte)
        if original is None:
            continue
        resultado.extend((metodo, original) for metodo in metodos(original))
    return resultado


def slugify(s, largo=80):
    s = re.sub(r"[^a-z0-9]+", "-", sin_tildes(s or "").lower()).strip("-")
    return s[:largo].rstrip("-") or "tramite"


def decodificar(contenido):
    # Los CSV de TAD en datos.gob.ar vienen en UTF-16 LE con BOM y separados por tabulaciones.
    if contenido[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return contenido.decode("utf-16")
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1")


def leer_csv(contenido):
    """Bytes de un CSV -> (columnas canónicas encontradas, filas como dict {COLUMNA: valor})."""
    texto_csv = decodificar(contenido)
    primera_linea = texto_csv.split("\n", 1)[0]
    delimitador = max(",;|\t", key=primera_linea.count)
    lector = csv.reader(io.StringIO(texto_csv, newline=""), delimiter=delimitador)
    try:
        encabezado = next(lector)
    except StopIteration:
        return [], []

    alias = {clave_columna(a): canonica for canonica, nombres in COLUMNAS.items() for a in nombres}
    columnas = [alias.get(clave_columna(c), clave_columna(c)) for c in encabezado]
    filas = []
    for valores in lector:
        if not any(v.strip() for v in valores):
            continue
        filas.append(dict(zip(columnas, valores)))
    return columnas, filas


def normalizar_fila(fila):
    """Fila cruda -> (registro, advertencias). registro es None si la fila no tiene ID válido."""
    advertencias = []

    def campo(nombre, funcion):
        try:
            return funcion(fila.get(nombre))
        except ValueError as e:
            advertencias.append(f"{nombre}: {e}")
            return None

    id_tramite = campo("ID_TRAMITE", entero)
    if id_tramite is None:
        return None, advertencias or ["fila sin ID_TRAMITE"]

    registro = {
        "id_tramite": id_tramite,
        "nombre": campo("NOMBRE_TRAMITE", texto),
        "organo_rector": campo("ORGANO_RECTOR", texto),
        "fecha_publicacion": campo("FECHA_PUBLICACION_PROD", fecha),
        "arancelado": campo("MARCA_ARANCELADO", booleano),
        "link": campo("LINK_DE_ACCESO", texto),
        "validadores": list(dict.fromkeys(original for _, original in campo("VALIDADOR_IDENTIDAD", validadores) or [])),
        "pago_minimo": campo("PAGO_MINIMO", monto),
        "pago_maximo": campo("PAGO_MAXIMO", monto),
        "pago_promedio": campo("PAGO_PROMEDIO", monto),
    }
    return registro, [f"ID {id_tramite}: {a}" for a in advertencias]


def a_json(valor):
    """Valores de un registro -> tipos serializables y estables (para jsonb y hash)."""
    if isinstance(valor, Decimal):
        return format(valor.quantize(Decimal("0.01")), "f")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: a_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [a_json(v) for v in valor]
    return valor


def hash_registro(datos):
    serializado = json.dumps(a_json(datos), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()
