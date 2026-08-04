import pandas as pd
import json
import streamlit as st
import requests
import io
from pathlib import Path

# URL Raw de GitHub para la matriz de cupos en vivo
URL_RAW_CUPOS = "https://raw.githubusercontent.com/NazthRM/FQ_hub.UNAM/refs/heads/main/Documentación/matriz_cupos.csv"

# Definir el directorio base de forma robusta para evitar errores en Streamlit Cloud
BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "Documentación"


@st.cache_data
def cargar_mapa_planes():
    """Lee los JSON de los planes de estudio y crea un diccionario maestro por Clave de materia."""
    mapa = {}
    ruta_planes = DOCS_DIR / "planes_estudio"

    if not ruta_planes.exists():
        st.warning(f"Advertencia: No se encontró la carpeta {ruta_planes}")
        return mapa

    # Diccionario para mapear las claves de tu JSON a nombres legibles
    nombres_carreras = {
        "Q": "Química",
        "IQ": "Ingeniería Química",
        "IQA": "Ingeniería Química Metalúrgica",
        "QA": "Química de Alimentos",
        "QFB": "Química Farmacéutico Biológica",
        "QIM": "Química e Ingeniería en Materiales",
    }

    # Iteramos sobre los archivos usando pathlib
    for archivo in ruta_planes.iterdir():
        if archivo.suffix == ".json":
            with open(archivo, "r", encoding="utf-8") as f:
                plan = json.load(f)

            # Obtenemos el nombre legible de la carrera
            clave_carrera = plan.get("clave_carrera", "")
            carrera_nombre = nombres_carreras.get(
                clave_carrera, plan.get("carrera", "Desconocida")
            )

            # Función interna para no repetir código al leer las materias
            def procesar_materia(mat, semestre="N/A"):
                clave = str(mat.get("clave", "")).strip()
                caracter_raw = str(mat.get("caracter", "")).strip().lower()

                # Normalización limpia leyendo directamente tu taxonomía
                if "semestre" in caracter_raw:
                    caracter_final = "Obligatoria"
                elif "disciplinaria" in caracter_raw:
                    caracter_final = "Disciplinaria"
                elif (
                    "sociohumanistica" in caracter_raw
                    or "sociohumanística" in caracter_raw
                ):
                    caracter_final = "Sociohumanística"
                elif "inorgánica" in caracter_raw or "inorganica" in caracter_raw:
                    caracter_final = "Inorgánica de Elección"
                else:
                    caracter_final = (
                        caracter_raw.capitalize() if caracter_raw else "Desconocido"
                    )

                if clave not in mapa:
                    mapa[clave] = []

                # Añadimos la relación Clave -> Carrera/Semestre/Caracter
                registro = {
                    "Carrera": carrera_nombre,
                    "Semestre": semestre,
                    "Caracter": caracter_final,
                }
                if registro not in mapa[clave]:
                    mapa[clave].append(registro)

            # 1. Extraemos materias de los semestres
            for sem_key, materias in plan.get("semestres", {}).items():
                sem_num = sem_key.replace("semestre_", "")
                for mat in materias:
                    procesar_materia(mat, semestre=sem_num)

            # 2. Extraemos el resto de las categorías (van sin semestre fijo, por ende "N/A")
            for mat in plan.get("optativas", []):
                procesar_materia(mat)
            for mat in plan.get("sociohumanisticas", []):
                procesar_materia(mat)
            for mat in plan.get("obligatorias_eleccion_inorganica", []):
                procesar_materia(mat)

    return mapa


@st.cache_data
def cargar_horarios_indexados():
    ruta_horarios = DOCS_DIR / "IDs_horarios_enriquecido.json"

    if not ruta_horarios.exists():
        st.warning(f"No se encontró el archivo de horarios en: {ruta_horarios}")
        return pd.DataFrame(), pd.DataFrame()

    with open(ruta_horarios, "r", encoding="utf-8") as f:
        datos = json.load(f)

    # Cargamos nuestro nuevo diccionario maestro
    mapa_planes = cargar_mapa_planes()

    filas = []
    relaciones_plan = []

    for item in datos:
        id_unico = item.get("id_unico", "")
        clave = str(item.get("clave", "")).strip()

        profesores_str = ", ".join(item.get("profesores", []))
        horarios_lista = item.get("horarios", [])
        horarios_str = (
            " | ".join(
                [
                    f"{h.get('dia', '')} {h.get('horas', '')} ({h.get('salon', 'S/S')})"
                    for h in horarios_lista
                ]
            )
            if horarios_lista
            else "Sin horario asignado"
        )

        # 1. Armamos la tabla base de materias/grupos
        filas.append(
            {
                "ID Único": id_unico,
                "Clave": clave,
                "Asignatura": str(item.get("asignatura", "")).strip().upper(),
                "Grupo": str(item.get("grupo", "")),
                "Tipo": item.get("tipo", "TEO/LAB"),
                "Créditos": item.get("creditos", 0),
                "Profesores": profesores_str,
                "Horarios": horarios_str,
            }
        )

        # 2. Cruzamos la Clave con nuestro mapa de planes de estudio
        info_planes = mapa_planes.get(clave, [])

        if not info_planes:
            relaciones_plan.append(
                {
                    "ID Único": id_unico,
                    "Carrera": "Desconocida",
                    "Semestre": "N/A",
                    "Caracter": "Desconocido",
                }
            )
        else:
            carreras_unicas = set(info["Carrera"] for info in info_planes)
            es_tronco_comun = len(carreras_unicas) >= 5

            if es_tronco_comun:
                semestre_tc = next(
                    (
                        info["Semestre"]
                        for info in info_planes
                        if info["Semestre"] != "N/A"
                    ),
                    "N/A",
                )
                relaciones_plan.append(
                    {
                        "ID Único": id_unico,
                        "Carrera": "Tronco Común",
                        "Semestre": semestre_tc,
                        "Caracter": "Obligatoria",
                    }
                )
            else:
                for info in info_planes:
                    relaciones_plan.append(
                        {
                            "ID Único": id_unico,
                            "Carrera": info["Carrera"],
                            "Semestre": info["Semestre"],
                            "Caracter": info["Caracter"],
                        }
                    )

    df_materias = pd.DataFrame(filas)
    df_relaciones = pd.DataFrame(relaciones_plan)

    # Eliminamos duplicados por si acaso
    df_relaciones = df_relaciones.drop_duplicates()

    return df_materias, df_relaciones


@st.cache_data(ttl=300)
def cargar_historico_en_vivo():
    try:
        # 1. Petición segura con timeout para evitar que la app se congele
        response = requests.get(URL_RAW_CUPOS, timeout=10)
        response.raise_for_status()  # Verifica que la respuesta sea 200 OK

        # 2. Leemos el texto de la respuesta con StringIO para Pandas
        df_live = pd.read_csv(io.StringIO(response.text))

        ruta_lb = DOCS_DIR / "matriz_cupos_LB.csv"

        if ruta_lb.exists():
            df_lb = pd.read_csv(ruta_lb)
            df_historico = pd.concat([df_lb, df_live], ignore_index=True)
        else:
            df_historico = df_live.copy()

        # Conversión de horas
        df_historico["Fecha_Hora_Extraccion"] = pd.to_datetime(
            df_historico["Fecha_Hora_Extraccion"], utc=True
        )
        df_historico["Fecha_Hora_Extraccion"] = (
            df_historico["Fecha_Hora_Extraccion"]
            .dt.tz_convert("America/Mexico_City")
            .dt.tz_localize(None)
        )

        df_historico = df_historico.drop_duplicates(
            subset=["id_unico", "Fecha_Hora_Extraccion"], keep="last"
        )
        df_historico = df_historico.sort_values(
            by=["id_unico", "Fecha_Hora_Extraccion"]
        ).reset_index(drop=True)

        return df_historico
    except requests.exceptions.RequestException as e:
        st.error(f"Error de red al conectar con el repositorio de GitHub: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error interno procesando el histórico de cupos: {e}")
        return pd.DataFrame()


@st.cache_data
def obtener_datos_fusionados():
    """Une la telemetría histórica con los detalles del grupo (para el predictor)."""
    df_horarios, _ = cargar_horarios_indexados()
    df_historico = cargar_historico_en_vivo()

    if df_historico.empty or df_horarios.empty:
        return pd.DataFrame()

    # Hacemos un JOIN usando el ID Único para traer nombres de materias al histórico
    df_fusionado = pd.merge(
        df_historico,
        df_horarios[["ID Único", "Clave", "Asignatura", "Grupo", "Profesores"]],
        left_on="id_unico",
        right_on="ID Único",
        how="left",
    )
    return df_fusionado
