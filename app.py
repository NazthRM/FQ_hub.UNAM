import datetime
import pandas as pd
import streamlit as st

# Carga de datos desde data_loader
from data_loader import (
    cargar_historico_en_vivo,
    cargar_horarios_indexados,
    obtener_datos_fusionados,
)

# Importamos el motor predictivo
from predictor import proyectar_supervivencia_hibrida

st.set_page_config(page_title="FQ Hub", layout="wide", page_icon="🧪")

# ==========================================
# 0. INICIALIZACIÓN DE MEMORIA (SESSION STATE)
# ==========================================
if "grupos_guardados" not in st.session_state:
    st.session_state.grupos_guardados = set()
elif isinstance(st.session_state.grupos_guardados, list):
    st.session_state.grupos_guardados = set(st.session_state.grupos_guardados)

# ==========================================
# 1. BARRA LATERAL (CONFIGURACIÓN)
# ==========================================
with st.sidebar:
    st.title("Hub de herramientas")
    st.divider()
    vista_actual = st.radio(
        "¿Qué es lo que deseas hacer?", ["Buscador de Grupos", "Predicción de cupo"]
    )
    st.divider()
    st.metric(label="Grupos guardados", value=len(st.session_state.grupos_guardados))

# ==========================================
# 2. CARGA DE DATOS
# ==========================================
df_horarios, df_relaciones = cargar_horarios_indexados()
df_historico = cargar_historico_en_vivo()
df_fusionado = obtener_datos_fusionados()

# ==========================================
# 3. ÁREA PRINCIPAL
# ==========================================
st.title("FQ Hub de Supervivencia")
st.markdown(
    "Bienvenido al Hub de herramientas para sobrevivir a la Facultad de Química"
)

if df_horarios.empty or df_relaciones.empty:
    st.error(
        "No se pudo cargar la base de datos de horarios. Verifica los archivos en la carpeta Documentación."
    )
else:
    # --- VISTA 1: BUSCADOR DE GRUPOS ---
    if vista_actual == "Buscador de Grupos":
        st.subheader("Buscador de Materias y Grupos")
        st.caption(
            "Filtra por plan de estudios, semestre y carácter, o busca directamente."
        )

        carreras_disponibles = ["Todas las carreras"] + sorted(
            [
                c
                for c in df_relaciones["Carrera"].unique()
                if c not in ["Tronco Común", "Desconocida"]
            ]
        )
        filtro_carrera = st.selectbox(
            "1. Plan de Estudios (Carrera):", options=carreras_disponibles
        )

        relaciones_filtradas = df_relaciones.copy()
        if filtro_carrera != "Todas las carreras":
            carreras_validas = {filtro_carrera, "Tronco Común"}
            relaciones_filtradas = relaciones_filtradas[
                relaciones_filtradas["Carrera"].isin(carreras_validas)
            ]

        semestres_disponibles = sorted(
            [s for s in relaciones_filtradas["Semestre"].unique() if s != "N/A"],
            key=int,
        )
        caracteres_disponibles = sorted(relaciones_filtradas["Caracter"].unique())

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_semestre = st.multiselect(
                "2. Semestre:", options=semestres_disponibles
            )
        with col_f2:
            filtro_caracter = st.multiselect(
                "3. Carácter:", options=caracteres_disponibles
            )

        if filtro_semestre:
            relaciones_filtradas = relaciones_filtradas[
                (relaciones_filtradas["Semestre"].isin(filtro_semestre))
                | (relaciones_filtradas["Semestre"] == "N/A")
            ]

        if filtro_caracter:
            relaciones_filtradas = relaciones_filtradas[
                relaciones_filtradas["Caracter"].isin(filtro_caracter)
            ]

        ids_validos = relaciones_filtradas["ID Único"].unique()
        df_filtrado = df_horarios[df_horarios["ID Único"].isin(ids_validos)].copy()

        materias_disponibles = sorted(df_filtrado["Asignatura"].unique())

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            filtro_materia = st.multiselect(
                "4. Asignatura(s):", options=materias_disponibles
            )
        with col_t2:
            filtro_profesor = st.text_input("Buscar por Profesor:")

        if filtro_materia:
            df_filtrado = df_filtrado[df_filtrado["Asignatura"].isin(filtro_materia)]

        if filtro_profesor:
            df_filtrado = df_filtrado[
                df_filtrado["Profesores"].str.contains(
                    filtro_profesor.strip().upper(), na=False
                )
            ]

        mostrar_tabla = True
        if (
            filtro_carrera != "Todas las carreras"
            and not filtro_materia
            and not filtro_profesor
            and not filtro_semestre
        ):
            mostrar_tabla = False
            st.info(
                "Selecciona un semestre, asignatura o ingresa un nombre de profesor para desplegar los grupos."
            )

        if mostrar_tabla:
            if df_filtrado.empty:
                st.warning(
                    "No se encontraron grupos que coincidan con los criterios seleccionados."
                )
            else:
                df_editor_data = df_filtrado.copy()
                df_editor_data.insert(
                    0,
                    "Guardar",
                    df_editor_data["ID Único"].isin(st.session_state.grupos_guardados),
                )

                df_editado = st.data_editor(
                    df_editor_data,
                    use_container_width=True,
                    hide_index=True,
                    disabled=[
                        "ID Único",
                        "Clave",
                        "Asignatura",
                        "Grupo",
                        "Tipo",
                        "Créditos",
                        "Profesores",
                        "Horarios",
                    ],
                    column_config={"ID Único": None},
                    key="editor_buscador",
                )

                if st.button("Actualizar mis grupos guardados", type="primary"):
                    seleccionados = set(
                        df_editado[df_editado["Guardar"] == True]["ID Único"]
                    )
                    deseleccionados = set(
                        df_editado[df_editado["Guardar"] == False]["ID Único"]
                    )

                    st.session_state.grupos_guardados.update(seleccionados)
                    st.session_state.grupos_guardados.difference_update(deseleccionados)

                    st.toast("Grupos guardados actualizados con éxito", icon="✅")
                    st.rerun()

    # --- VISTA 2: PREDICCIÓN DE CUPO ---
    elif vista_actual == "Predicción de cupo":
        st.subheader("Predicción de Cupo y Análisis de Horarios")

        if not df_historico.empty:
            ultima_lectura = (
                df_historico["Fecha_Hora_Extraccion"]
                .max()
                .strftime("%Y-%m-%d %H:%M:%S")
            )
            st.caption(
                f"🟢 **Telemetría en vivo conectada** | Última lectura capturada: `{ultima_lectura}`"
            )
        else:
            st.caption("🟡 **Conectando con el repositorio de datos...**")

        if not st.session_state.grupos_guardados:
            st.info(
                "Aún no has guardado ningún grupo. Utiliza el **Buscador de Grupos** para seleccionar materias."
            )
        else:
            df_guardados = df_horarios[
                df_horarios["ID Único"].isin(st.session_state.grupos_guardados)
            ].copy()

            # Cruzar con la telemetría en vivo para mostrar el cupo actual
            if not df_historico.empty and "id_unico" in df_historico.columns:
                df_ultimos_cupos = (
                    df_historico.sort_values("Fecha_Hora_Extraccion")
                    .groupby("id_unico")
                    .last()
                    .reset_index()
                )
                col_cupo = (
                    "cupo"
                    if "cupo" in df_ultimos_cupos.columns
                    else df_ultimos_cupos.columns[-1]
                )
                df_ultimos_cupos["Cupo Actual"] = (
                    df_ultimos_cupos[col_cupo]
                    .astype(str)
                    .str.replace("%", "")
                    .str.strip()
                    + "%"
                )
                df_guardados = pd.merge(
                    df_guardados,
                    df_ultimos_cupos[["id_unico", "Cupo Actual"]],
                    left_on="ID Único",
                    right_on="id_unico",
                    how="left",
                )
                df_guardados["Cupo Actual"] = df_guardados["Cupo Actual"].fillna("100%")
            else:
                df_guardados["Cupo Actual"] = "100%"

            cols_resumen = [
                "ID Único",
                "Clave",
                "Asignatura",
                "Grupo",
                "Tipo",
                "Cupo Actual",
                "Profesores",
                "Horarios",
            ]

            st.dataframe(
                df_guardados[cols_resumen], use_container_width=True, hide_index=True
            )

            st.divider()
            st.markdown("### 🎯 Mi Turno de Inscripción")
            st.caption(
                "Ingresa la fecha y hora exacta de tu turno para estimar si alcanzarás lugar."
            )

            col_d, col_h = st.columns(2)
            with col_d:
                dia_turno = st.date_input(
                    "Día asignado:",
                    value=datetime.date(2026, 8, 3),
                    min_value=datetime.date(2026, 8, 3),
                    max_value=datetime.date(2026, 8, 6),
                )

            with col_h:
                # Opciones de horario exacto cada 10 minutos (09:00 a 19:00 hrs)
                horas_opciones = []
                for h in range(9, 20):
                    for m in (0, 10, 20, 30, 40, 50):
                        if h == 19 and m > 0:
                            break
                        horas_opciones.append(datetime.time(h, m))

                hora_turno = st.selectbox(
                    "Hora asignada (CDMX):",
                    options=horas_opciones,
                    format_func=lambda t: t.strftime("%H:%M hrs"),
                )

            if st.button(
                "🔮 Calcular probabilidad de cupo",
                type="primary",
                use_container_width=True,
            ):
                fecha_turno_dt = datetime.datetime.combine(dia_turno, hora_turno)
                st.write(
                    f"### 📊 Proyección al {fecha_turno_dt.strftime('%d/%m/%Y %H:%M hrs')}"
                )

                for _, materia in df_guardados.iterrows():
                    id_unico = materia["ID Único"]

                    prediccion = proyectar_supervivencia_hibrida(
                        id_unico=id_unico,
                        fecha_turno=fecha_turno_dt,
                        df_historico=df_historico,
                        df_horarios=df_horarios,
                        df_relaciones=df_relaciones,
                    )

                    with st.expander(
                        f"📌 {materia['Asignatura']} | Grupo {materia['Grupo']} ({materia['Tipo']})",
                        expanded=True,
                    ):
                        c1, c2, c3 = st.columns(3)
                        c1.metric(
                            "Disponibilidad Estimada",
                            f"{prediccion['disponibilidad_estimada_pct']}%",
                        )
                        c2.metric(
                            "Probabilidad de Cierre",
                            f"{int(prediccion['probabilidad_cierre'] * 100)}%",
                        )

                        tendencia_str = prediccion["tendencia"]
                        if "Acelerando" in tendencia_str:
                            c3.error(f"⚠️ {tendencia_str}")
                        elif "Desacelerando" in tendencia_str:
                            c3.info(f"ℹ️ {tendencia_str}")
                        else:
                            c3.success(f"✅ {tendencia_str}")

                        st.caption(
                            f"⚙️ **Metadatos:** {prediccion['mediciones_usadas']} lectura(s) histórica(s) | "
                            f"Factor Multicarrera: `{prediccion['factores']['alpha_carreras']}x` | "
                            f"Presión Demográfica: `{prediccion['factores']['alpha_presion']}x`"
                        )

            st.divider()
            if st.button("Limpiar todos los grupos guardados", type="secondary"):
                st.session_state.grupos_guardados.clear()
                st.rerun()
