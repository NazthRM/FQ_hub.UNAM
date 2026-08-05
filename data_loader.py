import io
import json
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

URL_RAW_CUPOS = "https://raw.githubusercontent.com/NazthRM/FQ_hub.UNAM/refs/heads/main/Documentación/matriz_cupos.csv"

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "Documentación"


@st.cache_data
def cargar_mapa_planes():
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

                # NUEVA JERARQUÍA: Privilegiar categorías especiales antes que la temporalidad
                if "sociohumanistic" in caracter_raw:
                    caracter_final = "Sociohumanística"
                elif "disciplinaria" in caracter_raw:
                    caracter_final = "Disciplinaria"
                elif "inorganica" in caracter_raw or "inorgánica" in caracter_raw:
                    caracter_final = "Inorgánica de Elección"
                elif "semestre" in caracter_raw or semestre != "N/A":
                    caracter_final = "Obligatoria"
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

            for sem_key, materias in plan.get("semestres", {}).items():
                sem_num = sem_key.replace("semestre_", "")
                for mat in materias:
                    procesar_materia(
                        mat, semestre=sem_num, caracter_default="Obligatoria"
                    )

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
    filas, relaciones_plan = [], []

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
        info_planes = mapa_planes.get(clave, [])
        if info_planes:
            carreras_unicas = set(info["Carrera"] for info in info_planes)
            es_tronco_comun = len(carreras_unicas) >= 5

            # MANTENER la inyección estricta para cada carrera, preservando su semestre exacto y carácter exacto.
            for info in info_planes:
                relaciones_plan.append(
                    {
                        "ID Único": id_unico,
                        "Carrera": info["Carrera"],
                        "Semestre": info["Semestre"],
                        "Caracter": info["Caracter"],
                    }
                )
    return pd.DataFrame(filas), pd.DataFrame(relaciones_plan).drop_duplicates()


@st.cache_data
def obtener_horarios_filtrados(
    carrera="Todas las carreras", semestres=None, caracteres=None
):
    """Función unificada para filtrar horarios por carrera, semestre y carácter."""
    df_horarios, df_relaciones = cargar_horarios_indexados()
    if df_horarios.empty or df_relaciones.empty:
        return pd.DataFrame(), pd.DataFrame()

    relaciones_filtradas = df_relaciones.copy()

    if carrera != "Todas las carreras":
        carreras_validas = {carrera, "Tronco Común"}
        relaciones_filtradas = relaciones_filtradas[
            relaciones_filtradas["Carrera"].isin(carreras_validas)
        ]

    cond_semestre = (
        relaciones_filtradas["Semestre"].isin(semestres)
        if semestres
        else pd.Series(False, index=relaciones_filtradas.index)
    )
    cond_caracter = (
        relaciones_filtradas["Caracter"].isin(caracteres)
        if caracteres
        else pd.Series(False, index=relaciones_filtradas.index)
    )

    if semestres and caracteres:
        relaciones_filtradas = relaciones_filtradas[cond_semestre | cond_caracter]
    elif semestres:
        relaciones_filtradas = relaciones_filtradas[cond_semestre]
    elif caracteres:
        relaciones_filtradas = relaciones_filtradas[cond_caracter]

    ids_validos = relaciones_filtradas["ID Único"].unique()
    df_resultado = df_horarios[df_horarios["ID Único"].isin(ids_validos)].copy()

    return df_resultado, relaciones_filtradas


@st.cache_data(ttl=300)
def cargar_historico_en_vivo():
    try:
        response = requests.get(URL_RAW_CUPOS, timeout=10)
        response.raise_for_status()
        df_live = pd.read_csv(io.StringIO(response.text))

        ruta_lb = DOCS_DIR / "matriz_cupos_LB.csv"
        df_historico = (
            pd.concat([pd.read_csv(ruta_lb), df_live], ignore_index=True)
            if ruta_lb.exists()
            else df_live.copy()
        )

        df_historico["Fecha_Hora_Extraccion"] = (
            pd.to_datetime(df_historico["Fecha_Hora_Extraccion"], utc=True)
            .dt.tz_convert("America/Mexico_City")
            .dt.tz_localize(None)
        )

        return (
            df_historico.drop_duplicates(
                subset=["id_unico", "Fecha_Hora_Extraccion"], keep="last"
            )
            .sort_values(by=["id_unico", "Fecha_Hora_Extraccion"])
            .reset_index(drop=True)
        )
    except Exception as e:
        st.error(f"Error cargando histórico de cupos: {e}")
        return pd.DataFrame()


@st.cache_data
def enriquecer_con_ultimos_cupos(df_target):
    """Enriquece un DataFrame de grupos con la columna del último cupo registrado en telemetría."""
    df_historico = cargar_historico_en_vivo()
    df_res = df_target.copy()

    if not df_historico.empty and "id_unico" in df_historico.columns:
        df_ultimos = (
            df_historico.sort_values("Fecha_Hora_Extraccion")
            .groupby("id_unico")
            .last()
            .reset_index()
        )
        col_cupo = "cupo" if "cupo" in df_ultimos.columns else df_ultimos.columns[-1]
        df_ultimos["Cupo Actual"] = (
            df_ultimos[col_cupo].astype(str).str.replace("%", "").str.strip() + "%"
        )
        df_res = pd.merge(
            df_res,
            df_ultimos[["id_unico", "Cupo Actual"]],
            left_on="ID Único",
            right_on="id_unico",
            how="left",
        )
        df_res["Cupo Actual"] = df_res["Cupo Actual"].fillna("100%")
    else:
        df_res["Cupo Actual"] = "100%"

    return df_res


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

        df_lleno = df_g[df_g["cupo_num"] <= 0.0]
        if not df_lleno.empty:
            t_fin = df_lleno["Fecha_Hora_Extraccion"].iloc[0]
            hora_cierre_str = t_fin.strftime("%d/%m %H:%M")
        else:
            t_fin = df_g["Fecha_Hora_Extraccion"].iloc[-1]
            hora_cierre_str = "Aún Disponible"

        horas_activas = max(0.1, calcular_horas_activas_inscripcion(t_inicio, t_fin))
        velocidad_pct_hora = (cupo_inicial - cupo_actual) / horas_activas

        resultados.append(
            {
                "Profesor": prof,
                "Asignatura": grupo,
                "Velocidad Agotamiento": f"{round(velocidad_pct_hora, 1)}% / hr",
                "Hora de Cierre": hora_cierre_str,
                "velocidad_raw": velocidad_pct_hora,
            }
        )

    df_res = pd.DataFrame(resultados)
    return (
        df_res.sort_values("velocidad_raw", ascending=False).drop(
            columns=["velocidad_raw"]
        )
        if not df_res.empty
        else pd.DataFrame()
    )
