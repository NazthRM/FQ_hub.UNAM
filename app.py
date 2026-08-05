import datetime
import pandas as pd
import streamlit as st

from data_loader import (
    cargar_historico_en_vivo,
    cargar_horarios_indexados,
    obtener_datos_fusionados,
    obtener_leaderboard_profesores,
)
from predictor import proyectar_supervivencia_hibrida
from tramites_calendar import cargar_contenido_ics, obtener_df_tramites

st.set_page_config(page_title="FQ Hub", layout="wide", page_icon="🧪")

# ==========================================
# 0. INICIALIZACIÓN DE MEMORIA
# ==========================================
if "grupos_guardados" not in st.session_state:
    st.session_state.grupos_guardados = set()
elif isinstance(st.session_state.grupos_guardados, list):
    st.session_state.grupos_guardados = set(st.session_state.grupos_guardados)

if "carrera_seleccionada" not in st.session_state:
    st.session_state.carrera_seleccionada = "Todas las carreras"

# ==========================================
# 1. BARRA LATERAL
# ==========================================
with st.sidebar:
    st.title("Hub de Herramientas")
    st.divider()
    vista_actual = st.radio(
        "¿De que tipo es tu emergencia?",
        [
            "Buscador de Grupos",
            "Predicción de Cupo",
            "Generador de Horarios",
            "Leaderboard de Profesores",
            "Trámites FQ",
        ],
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

        # GRID 2 FILAS x 3 COLUMNAS PARA SELECCIÓN DE CARRERA
        st.markdown("**1. Plan de Estudios (Carrera):**")
        carreras_lista = [
            "Química Farmacéutico Biológica",
            "Ingeniería Química",
            "Química",
            "Química de Alimentos",
            "Ingeniería Química Metalúrgica",
            "Química e Ingeniería en Materiales",
        ]

        row1_c1, row1_c2, row1_c3 = st.columns(3)
        row2_c1, row2_c2, row2_c3 = st.columns(3)
        cols_grid = [row1_c1, row1_c2, row1_c3, row2_c1, row2_c2, row2_c3]

        for idx, c_nom in enumerate(carreras_lista):
            activo = st.session_state.carrera_seleccionada == c_nom
            label_btn = f"{'🟢' if activo else '⚪'} {c_nom}"
            if cols_grid[idx].button(
                label_btn, key=f"btn_carrera_{idx}", use_container_width=True
            ):
                st.session_state.carrera_seleccionada = c_nom
                st.rerun()

        todas_activo = st.session_state.carrera_seleccionada == "Todas las carreras"
        if st.button(
            f"{'🟢' if todas_activo else '⚪'} Mostrar todas las carreras",
            key="btn_todas_carreras",
            use_container_width=True,
        ):
            st.session_state.carrera_seleccionada = "Todas las carreras"
            st.rerun()

        # Filtrado base por carrera
        relaciones_filtradas = df_relaciones.copy()
        if st.session_state.carrera_seleccionada != "Todas las carreras":
            carreras_validas = {st.session_state.carrera_seleccionada, "Tronco Común"}
            relaciones_filtradas = relaciones_filtradas[
                relaciones_filtradas["Carrera"].isin(carreras_validas)
            ]

        semestres_disponibles = sorted(
            [s for s in relaciones_filtradas["Semestre"].unique() if s != "N/A"],
            key=int,
        )
        caracteres_disponibles = sorted(
            [c for c in relaciones_filtradas["Caracter"].unique() if c != "Desconocido"]
        )

        st.divider()
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_semestre = st.multiselect(
                "2. Semestre:", options=semestres_disponibles
            )
        with col_f2:
            filtro_caracter = st.multiselect(
                "3. Carácter:", options=caracteres_disponibles
            )

        # LÓGICA DE FILTRADO ADITIVA (UNIÓN NO RESTRICTIVA)
        cond_semestre = (
            relaciones_filtradas["Semestre"].isin(filtro_semestre)
            if filtro_semestre
            else pd.Series(False, index=relaciones_filtradas.index)
        )
        cond_caracter = (
            relaciones_filtradas["Caracter"].isin(filtro_caracter)
            if filtro_caracter
            else pd.Series(False, index=relaciones_filtradas.index)
        )

        if filtro_semestre and filtro_caracter:
            relaciones_filtradas = relaciones_filtradas[cond_semestre | cond_caracter]
        elif filtro_semestre:
            relaciones_filtradas = relaciones_filtradas[cond_semestre]
        elif filtro_caracter:
            relaciones_filtradas = relaciones_filtradas[cond_caracter]

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
            st.session_state.carrera_seleccionada != "Todas las carreras"
            and not filtro_materia
            and not filtro_profesor
            and not filtro_semestre
            and not filtro_caracter
        ):
            mostrar_tabla = False
            st.info(
                "Selecciona un semestre, carácter, asignatura o ingresa un nombre de profesor para desplegar los grupos."
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
                f"**Telemetría en vivo conectada** | Última lectura capturada: `{ultima_lectura}`"
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
            st.markdown("### Turno de Inscripción")
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
                "Calcular probabilidad de cupo",
                type="primary",
                use_container_width=True,
            ):
                fecha_turno_dt = datetime.datetime.combine(dia_turno, hora_turno)
                st.write(
                    f"### Proyección al {fecha_turno_dt.strftime('%d/%m/%Y %H:%M hrs')}"
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
                            c3.error(f" {tendencia_str}")
                        elif "Desacelerando" in tendencia_str:
                            c3.info(f" {tendencia_str}")
                        else:
                            c3.success(f" {tendencia_str}")

                        # CÓDIGO CORREGIDO Y SEGURO:
                        factores = prediccion.get("factores", {})
                        alpha_c = factores.get("alpha_carreras", 1.0)
                        alpha_p = factores.get("alpha_presion", 1.0)
                        factor_d = factores.get("factor_desborde", 1.0)

                        st.caption(
                            f"⚙️ **Metadatos:** {prediccion['mediciones_usadas']} lectura(s) histórica(s) | "
                            f"Multicarrera: `{alpha_c}x` | "
                            f"Presión Demográfica: `{alpha_p}x` | "
                            f"Factor Desborde: `{factor_d}x`"
                        )

            st.divider()
            if st.button("Limpiar todos los grupos guardados", type="secondary"):
                st.session_state.grupos_guardados.clear()
                st.rerun()

        # --- VISTA 3: GENERADOR DE HORARIOS (SOLVER) ---
    elif vista_actual == "Generador de Horarios":
        st.subheader("Generador Inteligente de Horarios")
        st.caption(
            "Filtra por plan de estudios, semestre y carácter, o busca directamente."
        )

        # GRID 2 FILAS x 3 COLUMNAS PARA SELECCIÓN DE CARRERA
        st.markdown("**1. Plan de Estudios (Carrera):**")
        carreras_lista = [
            "Química Farmacéutico Biológica",
            "Ingeniería Química",
            "Química",
            "Química de Alimentos",
            "Ingeniería Química Metalúrgica",
            "Química e Ingeniería en Materiales",
        ]

        row1_c1, row1_c2, row1_c3 = st.columns(3)
        row2_c1, row2_c2, row2_c3 = st.columns(3)
        cols_grid = [row1_c1, row1_c2, row1_c3, row2_c1, row2_c2, row2_c3]

        for idx, c_nom in enumerate(carreras_lista):
            activo = st.session_state.carrera_seleccionada == c_nom
            label_btn = f"{'🟢' if activo else '⚪'} {c_nom}"
            if cols_grid[idx].button(
                label_btn, key=f"btn_carrera_{idx}", use_container_width=True
            ):
                st.session_state.carrera_seleccionada = c_nom
                st.rerun()

        todas_activo = st.session_state.carrera_seleccionada == "Todas las carreras"
        if st.button(
            f"{'🟢' if todas_activo else '⚪'} Mostrar todas las carreras",
            key="btn_todas_carreras",
            use_container_width=True,
        ):
            st.session_state.carrera_seleccionada = "Todas las carreras"
            st.rerun()

        # Filtrado base por carrera
        relaciones_filtradas = df_relaciones.copy()
        if st.session_state.carrera_seleccionada != "Todas las carreras":
            carreras_validas = {st.session_state.carrera_seleccionada, "Tronco Común"}
            relaciones_filtradas = relaciones_filtradas[
                relaciones_filtradas["Carrera"].isin(carreras_validas)
            ]

        semestres_disponibles = sorted(
            [s for s in relaciones_filtradas["Semestre"].unique() if s != "N/A"],
            key=int,
        )
        caracteres_disponibles = sorted(
            [c for c in relaciones_filtradas["Caracter"].unique() if c != "Desconocido"]
        )

        st.divider()
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_semestre = st.multiselect(
                "2. Semestre:", options=semestres_disponibles
            )
        with col_f2:
            filtro_caracter = st.multiselect(
                "3. Carácter:", options=caracteres_disponibles
            )

        # LÓGICA DE FILTRADO ADITIVA (UNIÓN NO RESTRICTIVA)
        cond_semestre = (
            relaciones_filtradas["Semestre"].isin(filtro_semestre)
            if filtro_semestre
            else pd.Series(False, index=relaciones_filtradas.index)
        )
        cond_caracter = (
            relaciones_filtradas["Caracter"].isin(filtro_caracter)
            if filtro_caracter
            else pd.Series(False, index=relaciones_filtradas.index)
        )

        if filtro_semestre and filtro_caracter:
            relaciones_filtradas = relaciones_filtradas[cond_semestre | cond_caracter]
        elif filtro_semestre:
            relaciones_filtradas = relaciones_filtradas[cond_semestre]
        elif filtro_caracter:
            relaciones_filtradas = relaciones_filtradas[cond_caracter]

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
            st.session_state.carrera_seleccionada != "Todas las carreras"
            and not filtro_materia
            and not filtro_profesor
            and not filtro_semestre
            and not filtro_caracter
        ):
            mostrar_tabla = False
            st.info(
                "Selecciona un semestre, carácter, asignatura o ingresa un nombre de profesor para desplegar los grupos."
            )

        with st.expander("Restricciones de Tiempo y Bloques Reservados (Opcional)"):
            c1, c2 = st.columns(2)
            with c1:
                h_min = st.time_input(
                    "Hora mínima de entrada:", value=datetime.time(7, 0)
                )
            with c2:
                h_max = st.time_input(
                    "Hora máxima de salida:", value=datetime.time(21, 0)
                )

            st.markdown("**Bloque Reservado Libre (Ej. Comida, Gym):**")
            cb1, cb2, cb3 = st.columns(3)
            with cb1:
                dia_bloque = st.selectbox(
                    "Día:", ["Todos", "Lun", "Mar", "Mie", "Jue", "Vie"]
                )
            with cb2:
                h_ini_b = st.time_input("Inicio descanso:", value=datetime.time(13, 0))
            with cb3:
                h_fin_b = st.time_input("Fin descanso:", value=datetime.time(14, 0))

        if st.button("Generar Mejores Horarios", type="primary"):

            from solver import generar_combinaciones_horarios

            bloques_res = []
            if dia_bloque != "Todos":
                bloques_res.append(
                    {"dia": dia_bloque, "hora_inicio": h_ini_b, "hora_fin": h_fin_b}
                )
            else:
                for d in ["Lun", "Mar", "Mie", "Jue", "Vie"]:
                    bloques_res.append(
                        {"dia": d, "hora_inicio": h_ini_b, "hora_fin": h_fin_b}
                    )

            resultados = generar_combinaciones_horarios(
                materias_seleccionadas=filtro_materia,
                df_horarios=df_horarios,
                grupos_guardados_set=st.session_state.grupos_guardados,
                hora_min_inicio=h_min,
                hora_max_fin=h_max,
                bloques_reservados=bloques_res,
            )

            if not resultados:
                st.error(
                    "No se encontraron combinaciones compatibles sin empalmes para los filtros seleccionados."
                )
            else:
                st.success(f"¡Se encontraron {len(resultados)} combinaciones válidas!")
                for idx, res in enumerate(resultados):
                    comb = res["combinacion"]
                    with st.expander(
                        f"Opción #{idx+1} | Score: {res['score_compatibilidad']} pts",
                        expanded=(idx == 0),
                    ):
                        df_comb = pd.DataFrame(comb)[
                            [
                                "Clave",
                                "Asignatura",
                                "Grupo",
                                "Tipo",
                                "Profesores",
                                "Horarios",
                            ]
                        ]
                        st.dataframe(df_comb, use_container_width=True, hide_index=True)
                        st.download_button(
                            label="Exportar esta combinación a mi Calendario (.ics)",
                            file_name=f"horario_fq_opcion_{idx+1}.ics",
                            mime="text/calendar",
                            key=f"btn_ics_{idx}",
                        )

    # --- VISTA 4: LEADERBOARD DE PROFESORES ---
    elif vista_actual == "Leaderboard de Profesores":
        from data_loader import obtener_leaderboard_profesores

        st.subheader("Leaderboard de Profesores con Mayor Demanda")
        st.caption("Monitoreo en tiempo real de la velocidad de agotamiento de cupos.")

        df_leaderboard = obtener_leaderboard_profesores()
        if df_leaderboard.empty:
            st.info("Cargando datos de telemetría de profesores...")
        else:
            st.dataframe(df_leaderboard, use_container_width=True, hide_index=True)

    # --- VISTA 5: DÍAS DE TRÁMITES FQ (CALENDARIO ESCOLAR) ---
    elif vista_actual == "Trámites FQ":
        st.subheader("Calendario Oficial de Trámites FQ (Semestre 2027-1)")
        st.caption(
            "Consulta las fechas clave del semestre e impórtalas directamente a tu calendario personal."
        )

        st.download_button(
            label="Descargar e Inyectar Calendario de Trámites a mi Celular (.ics)",
            data=cargar_contenido_ics(),  # <-- Carga dinámicamente el archivo .ics completo
            file_name="Calendar_Tramites_FQ.ics",
            mime="text/calendar",
            type="primary",
            use_container_width=True,
        )

        st.divider()
        df_tramites = obtener_df_tramites()
        st.dataframe(df_tramites, use_container_width=True, hide_index=True)
