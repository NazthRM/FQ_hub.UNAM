import streamlit as st
import pandas as pd

# Importamos la nueva función fusionadora
from data_loader import (
    cargar_horarios_indexados,
    cargar_historico_en_vivo,
    obtener_datos_fusionados,
)

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
# 2. CARGA DE DATOS (Delegada 100% al loader)
# ==========================================
df_horarios, df_relaciones = cargar_horarios_indexados()
df_historico = cargar_historico_en_vivo()
df_fusionado = obtener_datos_fusionados()  # <--- Nuestro nuevo motor de datos

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

        carreras_disponibles = sorted(
            [c for c in df_relaciones["Carrera"].unique() if c != "Tronco Común"]
        )
        filtro_carrera = st.multiselect(
            "1. Plan de Estudios (Carrera):", options=carreras_disponibles
        )

        relaciones_filtradas = df_relaciones.copy()
        if filtro_carrera:
            carreras_validas = set(filtro_carrera) | {"Tronco Común"}
            relaciones_filtradas = relaciones_filtradas[
                relaciones_filtradas["Carrera"].isin(carreras_validas)
            ]

        # Limpiamos la extracción de semestres
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
            # Agregamos un switch elegante en lugar de forzar la lógica en el backend
            incluir_optativas = st.checkbox(
                "Incluir materias sin semestre fijo (Optativas/Sociohumanísticas)",
                value=True,
            )

        with col_f2:
            filtro_caracter = st.multiselect(
                "3. Carácter / Tipo:", options=caracteres_disponibles
            )

        # Lógica de filtrado limpia y sin cadenas de texto forzadas (Hardcoding)
        if filtro_semestre:
            if incluir_optativas:
                # Muestra los semestres elegidos O los que no tienen semestre ("N/A")
                relaciones_filtradas = relaciones_filtradas[
                    (relaciones_filtradas["Semestre"].isin(filtro_semestre))
                    | (relaciones_filtradas["Semestre"] == "N/A")
                ]
            else:
                relaciones_filtradas = relaciones_filtradas[
                    relaciones_filtradas["Semestre"].isin(filtro_semestre)
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
        if filtro_carrera and not filtro_materia and not filtro_profesor:
            mostrar_tabla = False
            st.info(
                "Selecciona al menos una asignatura o ingresa un nombre de profesor para desplegar los grupos."
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
            cols_resumen = [
                "ID Único",
                "Clave",
                "Asignatura",
                "Grupo",
                "Tipo",
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
                dia_turno = st.date_input("Día asignado:")
            with col_h:
                hora_turno = st.time_input("Hora asignada (CDMX):")

            if st.button(
                "🔮 Calcular probabilidad de cupo",
                type="primary",
                use_container_width=True,
            ):
                st.info(
                    f"Calculando predicción para el {dia_turno} a las {hora_turno}... (Algoritmo en construcción)"
                )
                # Aquí irá nuestra conexión con predictor.py

            st.divider()
            if st.button("Limpiar todos los grupos guardados", type="secondary"):
                st.session_state.grupos_guardados.clear()
                st.rerun()
