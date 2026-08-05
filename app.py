import datetime
import pandas as pd
import streamlit as st

from data_loader import (
    cargar_historico_en_vivo,
    cargar_horarios_indexados,
    enriquecer_con_ultimos_cupos,
    obtener_horarios_filtrados,
    obtener_leaderboard_profesores,
)
from predictor import proyectar_supervivencia_hibrida
from tramites_calendar import cargar_contenido_ics, obtener_df_tramites
from solver import construir_malla_semanal, generar_combinaciones_horarios

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
        "¿De qué tipo es tu emergencia?",
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
# 2. CARGA BASE DE DATOS
# ==========================================
df_horarios, df_relaciones = cargar_horarios_indexados()
df_historico = cargar_historico_en_vivo()

# ==========================================
# 3. ÁREA PRINCIPAL
# ==========================================
st.title("FQ Hub de Supervivencia")
st.markdown(
    "Bienvenido al Hub de herramientas para sobrevivir a la Facultad de Química"
)

if df_horarios.empty or df_relaciones.empty:
    st.error(
        "No se pudo cargar la base de datos de horarios. Verifica la carpeta Documentación."
    )
else:
    # 🎯 SELECTOR GLOBAL DE CARRERA (Disponible para todas las herramientas)
    st.markdown("**1. Plan de Estudios (Carrera):**")
    carreras_lista = [
        "Química Farmacéutico Biológica",
        "Ingeniería Química",
        "Química",
        "Química de Alimentos",
        "Ingeniería Química Metalúrgica",
        "Química e Ingeniería en Materiales",
    ]

    cols_grid = st.columns(3) + st.columns(3)
    for idx, c_nom in enumerate(carreras_lista):
        activo = st.session_state.carrera_seleccionada == c_nom
        if cols_grid[idx].button(
            f"{'🟢' if activo else '⚪'} {c_nom}",
            key=f"btn_carrera_global_{idx}",
            use_container_width=True,
        ):
            st.session_state.carrera_seleccionada = c_nom
            st.rerun()

    todas_activo = st.session_state.carrera_seleccionada == "Todas las carreras"
    if st.button(
        f"{'🟢' if todas_activo else '⚪'} Mostrar todas las carreras",
        key="btn_todas_carreras_global",
        use_container_width=True,
    ):
        st.session_state.carrera_seleccionada = "Todas las carreras"
        st.rerun()

    st.divider()

    # --- VISTA 1: BUSCADOR DE GRUPOS ---
    if vista_actual == "Buscador de Grupos":
        st.subheader("Buscador de Materias y Grupos")
        st.caption(
            "Filtra por plan de estudios, semestre y carácter, o busca directamente."
        )

        # Obtener datos de semestres/caracteres válidos según carrera
        _, rel_carrera = obtener_horarios_filtrados(
            carrera=st.session_state.carrera_seleccionada
        )
        semestres_disponibles = sorted(
            [s for s in rel_carrera["Semestre"].unique() if s != "N/A"], key=int
        )
        caracteres_disponibles = sorted(
            [
                c
                for c in rel_carrera["Caracter"].unique()
                if c not in ["Desconocido", "Obligatoria"]
            ]
        )

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_semestre = st.multiselect(
                "2. Semestre:", options=semestres_disponibles, key="busc_semestre"
            )
        with col_f2:
            filtro_caracter = st.multiselect(
                "3. Carácter:", options=caracteres_disponibles, key="busc_caracter"
            )

        # Aplicar filtrado desde data_loader
        df_filtrado, _ = obtener_horarios_filtrados(
            carrera=st.session_state.carrera_seleccionada,
            semestres=filtro_semestre,
            caracteres=filtro_caracter,
        )

        materias_disponibles = sorted(df_filtrado["Asignatura"].unique())

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            filtro_materia = st.multiselect(
                "4. Asignatura(s):", options=materias_disponibles, key="busc_materia"
            )
        with col_t2:
            filtro_profesor = st.text_input("Buscar por Profesor:", key="busc_profesor")

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

                if st.button(
                    "Actualizar mis grupos guardados",
                    type="primary",
                    key="btn_actualizar_guardados",
                ):
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
    elif vista_actual == "Predicción de Cupo":
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
            df_guardados = enriquecer_con_ultimos_cupos(df_guardados)

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
                    key="pred_dia",
                )

            with col_h:
                horas_opciones = [
                    datetime.time(h, m)
                    for h in range(9, 20)
                    for m in (0, 10, 20, 30, 40, 50)
                    if not (h == 19 and m > 0)
                ]
                hora_turno = st.selectbox(
                    "Hora asignada (CDMX):",
                    options=horas_opciones,
                    format_func=lambda t: t.strftime("%H:%M hrs"),
                    key="pred_hora",
                )

            if st.button(
                "Calcular probabilidad de cupo",
                type="primary",
                use_container_width=True,
                key="btn_calc_cupo",
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

                        factores = prediccion.get("factores", {})
                        st.caption(
                            f"⚙️ **Metadatos:** {prediccion['mediciones_usadas']} lectura(s) histórica(s) | "
                            f"Multicarrera: `{factores.get('alpha_carreras', 1.0)}x` | "
                            f"Presión Demográfica: `{factores.get('alpha_presion', 1.0)}x` | "
                            f"Factor Desborde: `{factores.get('factor_desborde', 1.0)}x`"
                        )

            st.divider()
            if st.button(
                "Limpiar todos los grupos guardados",
                type="secondary",
                key="btn_limpiar_guardados",
            ):
                st.session_state.grupos_guardados.clear()
                st.rerun()

    # --- VISTA 3: GENERADOR DE HORARIOS (SOLVER) ---
    elif vista_actual == "Generador de Horarios":
        st.subheader("Generador Inteligente de Horarios")
        st.caption(
            f"Mostrando materias para: **{st.session_state.carrera_seleccionada}**"
        )

        # 1. Obtener datos de semestres/caracteres válidos según carrera
        _, rel_carrera_gen = obtener_horarios_filtrados(
            carrera=st.session_state.carrera_seleccionada
        )
        semestres_disp_gen = sorted(
            [s for s in rel_carrera_gen["Semestre"].unique() if s != "N/A"], key=int
        )
        caracteres_disp_gen = sorted(
            [
                c
                for c in rel_carrera_gen["Caracter"].unique()
                if c not in ["Desconocido", "Obligatoria"]
            ]
        )

        # 2. Filtros intermedios para no saturar el multiselect
        st.markdown("**1. Filtros opcionales para acortar la lista de asignaturas:**")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            filtro_sem_gen = st.multiselect(
                "Filtrar por Semestre:", options=semestres_disp_gen, key="gen_semestre"
            )
        with col_g2:
            filtro_car_gen = st.multiselect(
                "Filtrar por Carácter:", options=caracteres_disp_gen, key="gen_caracter"
            )

        # 3. Filtrar DataFrame por carrera, semestre y carácter
        df_horarios_generador, _ = obtener_horarios_filtrados(
            carrera=st.session_state.carrera_seleccionada,
            semestres=filtro_sem_gen,
            caracteres=filtro_car_gen,
        )

        df_horarios_generador = enriquecer_con_ultimos_cupos(df_horarios_generador)

        st.divider()

        # 4. Selección de Asignaturas y Configuración Dinámica Componente por Componente
        st.markdown("**2. Selección y Configuración de Asignaturas:**")
        materias_disponibles = sorted(df_horarios_generador["Asignatura"].unique())

        asig_elegidas = st.multiselect(
            "Selecciona tus Asignaturas Objetivo:",
            options=materias_disponibles,
            key="gen_asig_objetivo",
        )

        configuracion_materias = []

        if asig_elegidas:
            # Identificar materias que tienen más de un tipo (ej. Teoría + Lab / Experimental)
            materias_multi_tipo = [
                a
                for a in asig_elegidas
                if len(
                    df_horarios_generador[df_horarios_generador["Asignatura"] == a][
                        "Tipo"
                    ].unique()
                )
                > 1
            ]

            if materias_multi_tipo:
                st.caption(
                    "📌 **Ajuste Fino:** Desmarca los componentes que NO necesites cursar en este semestre."
                )

                for asig in materias_multi_tipo:
                    tipos_materia = df_horarios_generador[
                        df_horarios_generador["Asignatura"] == asig
                    ]["Tipo"].unique()

                    st.markdown(f"**{asig}**")
                    cols = st.columns(len(tipos_materia))
                    tipos_seleccionados = []

                    for i, tipo in enumerate(tipos_materia):
                        if cols[i].checkbox(tipo, value=True, key=f"chk_{asig}_{tipo}"):
                            tipos_seleccionados.append(tipo)

                    configuracion_materias.append(
                        {"asignatura": asig, "tipos": tipos_seleccionados}
                    )
                    st.write("")

            # Agregar materias simples (de un solo tipo) automáticamente
            for asig in asig_elegidas:
                if asig not in materias_multi_tipo:
                    tipos_materia = df_horarios_generador[
                        df_horarios_generador["Asignatura"] == asig
                    ]["Tipo"].unique()
                    configuracion_materias.append(
                        {"asignatura": asig, "tipos": list(tipos_materia)}
                    )

        # Control de disponibilidad
        solo_disponibles = st.toggle(
            "Excluir grupos sin cupo disponible",
            value=True,
            help="Si está activo, el generador ignorará los grupos que tengan 0% de lugares según la última lectura en vivo.",
        )

        # 5. Sistema de Veto de Profesores
        st.divider()
        st.markdown("**3. Control de Profesores (Veto):**")
        lista_profesores_cruda = set()
        for prof_str in df_horarios_generador["Profesores"].dropna():
            for p in str(prof_str).split(","):
                if p.strip() and p.strip().upper() != "POR ASIGNAR":
                    lista_profesores_cruda.add(p.strip())

        profesores_vetados = st.multiselect(
            "Vetar Profesores (Excluir de mis horarios):",
            options=sorted(list(lista_profesores_cruda)),
            key="gen_veto_profes",
            help="El generador ignorará cualquier combinación que incluya a estos profesores.",
        )

        # 6. Restricciones de Tiempo y Bloques Reservados
        with st.expander("Restricciones de Tiempo y Bloques Reservados (Opcional)"):
            c1, c2 = st.columns(2)
            with c1:
                h_min = st.time_input(
                    "Hora mínima de entrada:",
                    value=datetime.time(7, 0),
                    key="gen_h_min",
                )
            with c2:
                h_max = st.time_input(
                    "Hora máxima de salida:",
                    value=datetime.time(21, 0),
                    key="gen_h_max",
                )

            st.markdown("**Bloque Reservado Libre (Ej. Comida, Gym):**")
            cb1, cb2, cb3 = st.columns(3)
            with cb1:
                dia_bloque = st.selectbox(
                    "Día:",
                    ["Todos", "Lun", "Mar", "Mie", "Jue", "Vie"],
                    key="gen_dia_bloque",
                )
            with cb2:
                h_ini_b = st.time_input(
                    "Inicio descanso:", value=datetime.time(13, 0), key="gen_h_ini_b"
                )
            with cb3:
                h_fin_b = st.time_input(
                    "Fin descanso:", value=datetime.time(14, 0), key="gen_h_fin_b"
                )

        # 7. Ejecución con Solver Refactorizado
        if st.button(
            "🚀 Generar Mejores Horarios", type="primary", key="btn_generar_horarios"
        ):
            if not asig_elegidas:
                st.warning(
                    "Debes seleccionar al menos una asignatura para generar combinaciones."
                )
            else:
                from solver import generar_combinaciones_horarios

                bloques_res = (
                    [{"dia": dia_bloque, "hora_inicio": h_ini_b, "hora_fin": h_fin_b}]
                    if dia_bloque != "Todos"
                    else [
                        {"dia": d, "hora_inicio": h_ini_b, "hora_fin": h_fin_b}
                        for d in ["Lun", "Mar", "Mie", "Jue", "Vie"]
                    ]
                )

                # Se envía configuracion_materias y profesores_vetados al solver
                resultados = generar_combinaciones_horarios(
                    configuracion_materias=configuracion_materias,
                    df_horarios=df_horarios_generador,
                    grupos_guardados_set=st.session_state.grupos_guardados,
                    hora_min_inicio=h_min,
                    hora_max_fin=h_max,
                    bloques_reservados=bloques_res,
                    profesores_vetados=profesores_vetados,
                    solo_disponibles=solo_disponibles,
                )

                if not resultados:
                    st.error(
                        "No se encontraron combinaciones compatibles sin empalmes. Prueba desmarcando profesores vetados o reduciendo bloques reservados."
                    )
                else:
                    st.success(
                        f"¡Se encontraron {len(resultados)} combinaciones válidas!"
                    )
                    for idx, res in enumerate(resultados):
                        comb = res["combinacion"]
                        with st.expander(
                            f"Opción #{idx+1} | Score: {res['score_compatibilidad']} pts",
                            expanded=(idx == 0),
                        ):
                            # 1. Pestañas para elegir entre Vista Gráfica (Malla) y Vista Detallada (Tabla)
                            tab_malla, tab_detalles = st.tabs(
                                ["Malla Semanal Visual", "Lista de Grupos"]
                            )

                        with tab_malla:
                            from solver import construir_malla_semanal

                            df_malla = construir_malla_semanal(comb)

                            if df_malla.empty:
                                st.info(
                                    "No hay horarios asignados para graficar en la malla."
                                )
                            else:
                                st.dataframe(
                                    df_malla, use_container_width=True, height=380
                                )

                        with tab_detalles:
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
                            st.dataframe(
                                df_comb, use_container_width=True, hide_index=True
                            )

                        # 2. Botón opcional de exportación a .ics
                        st.divider()
                        ics_lines = [
                            "BEGIN:VCALENDAR",
                            "VERSION:2.0",
                            "PRODID:-//FQ Hub UNAM//Generador Horarios//ES",
                        ]
                        for item in comb:
                            ics_lines.append("BEGIN:VEVENT")
                            ics_lines.append(
                                f"SUMMARY:{item['Asignatura']} (Gpo {item['Grupo']})"
                            )
                            ics_lines.append(
                                f"DESCRIPTION:Prof: {item['Profesores']} | Tipo: {item['Tipo']}"
                            )
                            ics_lines.append(
                                f"LOCATION:{item.get('Horarios', 'Sin aula')}"
                            )
                            ics_lines.append("END:VEVENT")
                        ics_lines.append("END:VCALENDAR")

                        st.download_button(
                            label="📥 Exportar esta opción a mi Google Calendar / Apple (.ics)",
                            data="\n".join(ics_lines),
                            file_name=f"horario_fq_opcion_{idx+1}.ics",
                            mime="text/calendar",
                            key=f"btn_ics_{idx}",
                        )

    # --- VISTA 4: LEADERBOARD DE PROFESORES ---
    elif vista_actual == "Leaderboard de Profesores":
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
            data=cargar_contenido_ics(),
            file_name="Calendar_Tramites_FQ.ics",
            mime="text/calendar",
            type="primary",
            use_container_width=True,
            key="btn_descarga_ics_tramites",
        )

        st.divider()
        st.dataframe(obtener_df_tramites(), use_container_width=True, hide_index=True)
