import io
import json
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

# URL Raw de GitHub para la matriz de cupos en vivo
URL_RAW_CUPOS = "https://raw.githubusercontent.com/NazthRM/FQ_hub.UNAM/refs/heads/main/Documentación/matriz_cupos.csv"

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "Documentación"


@st.cache_data
def cargar_mapa_planes():
    """Lee los JSON de los planes de estudio y mapea correctamente cada categoría."""
    mapa = {}
    ruta_planes = DOCS_DIR / "planes_estudio"

    if not ruta_planes.exists():
        st.warning(f"Advertencia: No se encontró la carpeta {ruta_planes}")
        return mapa

    nombres_carreras = {
        "Q": "Química",
        "IQ": "Ingeniería Química",
        "IQM": "Ingeniería Química Metalúrgica",
        "QA": "Química de Alimentos",
        "QFB": "Química Farmacéutico Biológica",
        "QIM": "Química e Ingeniería en Materiales",
    }

    for archivo in ruta_planes.iterdir():
        if archivo.suffix == ".json":
            with open(archivo, "r", encoding="utf-8") as f:
                plan = json.load(f)

            clave_carrera = plan.get("clave_carrera", "")
            carrera_nombre = nombres_carreras.get(
                clave_carrera, plan.get("carrera", "Desconocida")
            )

            def procesar_materia(mat, semestre="N/A", caracter_default="Optativa"):
                clave = str(mat.get("clave", "")).strip()
                caracter_raw = str(mat.get("caracter", "")).strip().lower()

                if "semestre" in caracter_raw or semestre != "N/A":
                    caracter_final = "Obligatoria"
                elif (
                    "sociohumanistica" in caracter_raw
                    or "sociohumanística" in caracter_raw
                ):
                    caracter_final = "Sociohumanística"
                elif "inorgánica" in caracter_raw or "inorganica" in caracter_raw:
                    caracter_final = "Inorgánica de Elección"
                elif "disciplinaria" in caracter_raw:
                    caracter_final = "Disciplinaria"
                else:
                    caracter_final = caracter_default

                if clave not in mapa:
                    mapa[clave] = []

                registro = {
                    "Carrera": carrera_nombre,
                    "Semestre": semestre,
                    "Caracter": caracter_final,
                }
                if registro not in mapa[clave]:
                    mapa[clave].append(registro)

            # 1. Semestres (Obligatorias)
            for sem_key, materias in plan.get("semestres", {}).items():
                sem_num = sem_key.replace("semestre_", "")
                for mat in materias:
                    procesar_materia(
                        mat, semestre=sem_num, caracter_default="Obligatoria"
                    )

            # 2. Categorías fuera de semestre
            for mat in plan.get("optativas", []):
                procesar_materia(mat, caracter_default="Optativa")
            for mat in plan.get("sociohumanisticas", []):
                procesar_materia(mat, caracter_default="Sociohumanística")
            for mat in plan.get("obligatorias_eleccion_inorganica", []):
                procesar_materia(mat, caracter_default="Inorgánica de Elección")

    return mapa


@st.cache_data
def cargar_horarios_indexados():
    ruta_horarios = DOCS_DIR / "IDs_horarios_enriquecido.json"

    if not ruta_horarios.exists():
        st.warning(f"No se encontró el archivo de horarios en: {ruta_horarios}")
        return pd.DataFrame(), pd.DataFrame()

    with open(ruta_horarios, "r", encoding="utf-8") as f:
        datos = json.load(f)

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

        info_planes = mapa_planes.get(clave, [])

        if info_planes:
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
    df_relaciones = pd.DataFrame(relaciones_plan).drop_duplicates()

    return df_materias, df_relaciones


@st.cache_data(ttl=300)
def cargar_historico_en_vivo():
    try:
        response = requests.get(URL_RAW_CUPOS, timeout=10)
        response.raise_for_status()
        df_live = pd.read_csv(io.StringIO(response.text))

        ruta_lb = DOCS_DIR / "matriz_cupos_LB.csv"
        if ruta_lb.exists():
            df_lb = pd.read_csv(ruta_lb)
            df_historico = pd.concat([df_lb, df_live], ignore_index=True)
        else:
            df_historico = df_live.copy()

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
    except Exception as e:
        st.error(f"Error cargando histórico de cupos: {e}")
        return pd.DataFrame()


@st.cache_data
def obtener_datos_fusionados():
    df_horarios, _ = cargar_horarios_indexados()
    df_historico = cargar_historico_en_vivo()

    if df_historico.empty or df_horarios.empty:
        return pd.DataFrame()

    return pd.merge(
        df_historico,
        df_horarios[["ID Único", "Clave", "Asignatura", "Grupo", "Profesores"]],
        left_on="id_unico",
        right_on="ID Único",
        how="left",
    )


@st.cache_data(ttl=300)
def obtener_leaderboard_profesores():
    """Calcula el ranking de profesores con grupos más demandados y su velocidad de agotamiento."""
    from predictor import calcular_horas_activas_inscripcion

    df_fusionado = obtener_datos_fusionados()
    if df_fusionado.empty:
        return pd.DataFrame()

    col_cupo = "cupo" if "cupo" in df_fusionado.columns else df_fusionado.columns[-1]

    df_fusionado["cupo_num"] = pd.to_numeric(
        df_fusionado[col_cupo].astype(str).str.replace("%", "").str.strip(),
        errors="coerce",
    )

    resultados = []
    for (prof, clave, grupo), df_g in df_fusionado.groupby(
        ["Profesores", "Clave", "Asignatura"]
    ):
        if not prof or prof == "POR ASIGNAR":
            continue

        df_g = df_g.sort_values("Fecha_Hora_Extraccion")
        cupo_inicial = df_g["cupo_num"].iloc[0]
        cupo_actual = df_g["cupo_num"].iloc[-1]

        t_inicio = df_g["Fecha_Hora_Extraccion"].iloc[0]
        t_ultimo = df_g["Fecha_Hora_Extraccion"].iloc[-1]

        horas_activas = max(0.1, calcular_horas_activas_inscripcion(t_inicio, t_ultimo))
        velocidad_pct_hora = (cupo_inicial - cupo_actual) / horas_activas

        df_lleno = df_g[df_g["cupo_num"] <= 0.0]
        hora_cierre_str = (
            df_lleno["Fecha_Hora_Extraccion"].iloc[0].strftime("%d/%m %H:%M")
            if not df_lleno.empty
            else "Aún Disponible"
        )

        resultados.append(
            {
                "Profesor": prof,
                "Asignatura": grupo,
                "Cupo Actual": f"{cupo_actual}%",
                "Velocidad Agotamiento": f"{round(velocidad_pct_hora, 1)}% / hr",
                "Hora de Cierre": hora_cierre_str,
                "velocidad_raw": velocidad_pct_hora,
            }
        )

    df_res = pd.DataFrame(resultados)
    if not df_res.empty:
        df_res = df_res.sort_values("velocidad_raw", ascending=False).drop(
            columns=["velocidad_raw"]
        )

    return df_res
