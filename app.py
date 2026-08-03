import streamlit as st
import json
import os
import pandas as pd

st.set_page_config(page_title="FQ Hub", layout="wide", page_icon="🧪")

# URL Raw de GitHub para la matriz de cupos en vivo
URL_RAW_CUPOS = "https://raw.githubusercontent.com/NazthRM/rastreocuposfq/main/Documentaci%C3%B3n/matriz_cupos.csv"

# ==========================================
# 0. INICIALIZACIÓN DE MEMORIA (SESSION STATE)
# ==========================================
if 'grupos_guardados' not in st.session_state:
    st.session_state.grupos_guardados = set()
elif isinstance(st.session_state.grupos_guardados, list):
    st.session_state.grupos_guardados = set(st.session_state.grupos_guardados)

# ==========================================
# 1. FUNCIONES DE CARGA Y PROCESAMIENTO DE DATOS
# ==========================================
@st.cache_data
def cargar_horarios_indexados():
    ruta_horarios = os.path.join("Documentación", "IDs_horarios_enriquecido.json")
    
    if not os.path.exists(ruta_horarios):
        return pd.DataFrame(), pd.DataFrame()

    with open(ruta_horarios, 'r', encoding='utf-8') as f:
        datos = json.load(f)
        
    filas = []
    relaciones_plan = []

    for item in datos:
        id_unico = item.get("id_unico", "")
        profesores_str = ", ".join(item.get("profesores", []))
        horarios_lista = item.get("horarios", [])
        horarios_str = " | ".join([
            f"{h.get('dia', '')} {h.get('horas', '')} ({h.get('salon', 'S/S')})" 
            for h in horarios_lista
        ]) if horarios_lista else "Sin horario asignado"

        # Tabla base de materias/grupos
        filas.append({
            "ID Único": id_unico,
            "Clave": item.get("clave", ""),
            "Asignatura": str(item.get("asignatura", "")).strip().upper(),
            "Grupo": str(item.get("grupo", "")),
            "Tipo": item.get("tipo", "TEO/LAB"),
            "Créditos": item.get("creditos", 0),
            "Profesores": profesores_str,
            "Horarios": horarios_str
        })

        carreras_lista = item.get("carreras_asociadas", [])
        if not carreras_lista:
            carreras_lista = [{"carrera": "Tronco Común", "semestre": "", "caracter": ""}]

        for c in carreras_lista:
            carrera = str(c.get("carrera", "")).strip()
            if carrera in ["DESCONOCIDA", ""]:
                carrera = "Tronco Común"
                
            semestre_raw = str(c.get("semestre", "")).strip()
            caracter_raw = str(c.get("caracter", "")).strip().upper()

            # Normalización basada ÚNICAMENTE en el campo 'caracter' del JSON
            if "SOCIOHUMAN" in caracter_raw:
                caracter_final = "Sociohumanística"
                carrera = "Tronco Común"
            elif "OPTATIVA" in caracter_raw or "DISCIPLINAR" in caracter_raw:
                caracter_final = "Disciplinaria"
            elif "INORG" in caracter_raw:
                caracter_final = "Inorgánica"
            elif semestre_raw.isdigit() or "OBLIGATORIA" in caracter_raw or "SEMESTRE" in caracter_raw:
                caracter_final = "Obligatoria"
            else:
                caracter_final = "Disciplinaria"

            relaciones_plan.append({
                "ID Único": id_unico,
                "Carrera": carrera,
                "Semestre": semestre_raw if semestre_raw.isdigit() else "N/A",
                "Caracter": caracter_final
            })

    df_materias = pd.DataFrame(filas)
    df_relaciones = pd.DataFrame(relaciones_plan)
    
    return df_materias, df_relaciones

@st.cache_data(ttl=300) # Se refresca automáticamente cada 5 minutos
def cargar_historico_en_vivo():
    try:
        # 1. Leer directamente del Raw de GitHub
        df_live = pd.read_csv(URL_RAW_CUPOS)
        df_live["Fecha_Hora_Extraccion"] = pd.to_datetime(df_live["Fecha_Hora_Extraccion"])
        
        # 2. PARCHE DINÁMICO (Línea base del 3 de agosto)
        # Reasigna lecturas previas a las 09:00:00 para mantener el t0 exacto
        es_hoy_madrugada = (df_live["Fecha_Hora_Extraccion"].dt.date == pd.to_datetime("2026-08-03").date()) & \
                           (df_live["Fecha_Hora_Extraccion"].dt.hour < 9)
        
        df_live.loc[es_hoy_madrugada, "Fecha_Hora_Extraccion"] = pd.to_datetime("2026-08-03 09:00:00")
        
        # 3. Ordenar cronológicamente para cálculos de regresión
        df_live = df_live.sort_values(by=["id_unico", "Fecha_Hora_Extraccion"])
        
        return df_live
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 2. BARRA LATERAL (CONFIGURACIÓN)
# ==========================================
with st.sidebar:
    st.title("Hub de herramientas")
    st.divider()
    vista_actual = st.radio(
        "¿Qué es lo que deseas hacer?", 
        ["Buscador de Grupos", "Predicción de cupo"]
    )
    st.divider()
    st.metric(label="Grupos guardados", value=len(st.session_state.grupos_guardados))

# ==========================================
# 3. ÁREA PRINCIPAL
# ==========================================
st.title("FQ Hub de Supervivencia")
st.markdown("Bienvenido al Hub de herramientas para sobrevivir a la Facultad de Química")

df_horarios, df_relaciones = cargar_horarios_indexados()
df_historico = cargar_historico_en_vivo()

if df_horarios.empty or df_relaciones.empty:
    st.error("No se encontró o no se pudo procesar el archivo JSON de horarios en 'Documentación/IDs_horarios_enriquecido.json'.")
else:
    # --- VISTA 1: BUSCADOR DE GRUPOS ---
    if vista_actual == "Buscador de Grupos":
        st.subheader("Buscador de Materias y Grupos")
        st.caption("Filtra por plan de estudios, semestre y carácter, o busca directamente por asignatura o profesor.")

        # Obtener carreras únicas
        carreras_disponibles = sorted([c for c in df_relaciones["Carrera"].unique() if c != "Tronco Común"])
        
        # 1. Filtro Principal de Carrera
        filtro_carrera = st.multiselect("1. Plan de Estudios (Carrera):", options=carreras_disponibles)

        relaciones_filtradas = df_relaciones.copy()
        if filtro_carrera:
            carreras_validas = set(filtro_carrera) | {"Tronco Común"}
            relaciones_filtradas = relaciones_filtradas[relaciones_filtradas["Carrera"].isin(carreras_validas)]

        # 2. Semestres y Caracteres válidos según carreras seleccionadas
        semestres_disponibles = sorted(
            [s for s in relaciones_filtradas["Semestre"].unique() if s != "N/A"], 
            key=int
        )
        caracteres_disponibles = sorted(relaciones_filtradas["Caracter"].unique())

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_semestre = st.multiselect("2. Semestre:", options=semestres_disponibles)
        with col_f2:
            filtro_caracter = st.multiselect("3. Carácter / Tipo:", options=caracteres_disponibles)

        # 3. Aplicar Filtros Secundarios sobre la tabla relacional
        if filtro_semestre:
            relaciones_filtradas = relaciones_filtradas[
                (relaciones_filtradas["Semestre"].isin(filtro_semestre)) | 
                (relaciones_filtradas["Caracter"].isin(["Disciplinaria", "Inorgánica", "Sociohumanística"]))
            ]

        if filtro_caracter:
            relaciones_filtradas = relaciones_filtradas[relaciones_filtradas["Caracter"].isin(filtro_caracter)]

        # Cruce por ID Único sin alterar el DataFrame base
        ids_validos = relaciones_filtradas["ID Único"].unique()
        df_filtrado = df_horarios[df_horarios["ID Único"].isin(ids_validos)].copy()

        # 4. Búsqueda Directa por Asignatura o Profesor
        materias_disponibles = sorted(df_filtrado["Asignatura"].unique())

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            filtro_materia = st.multiselect("4. Asignatura(s):", options=materias_disponibles)
        with col_t2:
            filtro_profesor = st.text_input("Buscar por Profesor:")

        if filtro_materia:
            df_filtrado = df_filtrado[df_filtrado["Asignatura"].isin(filtro_materia)]

        if filtro_profesor:
            df_filtrado = df_filtrado[df_filtrado["Profesores"].str.contains(filtro_profesor.strip().upper(), na=False)]

        # Regla de visualización
        mostrar_tabla = True
        if filtro_carrera and not filtro_materia and not filtro_profesor:
            mostrar_tabla = False
            st.info("Selecciona al menos una asignatura o ingresa un nombre de profesor para desplegar los grupos.")

        if mostrar_tabla:
            if df_filtrado.empty:
                st.warning("No se encontraron grupos que coincidan con los criterios seleccionados.")
            else:
                df_editor_data = df_filtrado[[
                    "ID Único", "Clave", "Asignatura", "Grupo", "Tipo",
                    "Créditos", "Profesores", "Horarios"
                ]].copy()
                
                df_editor_data.insert(0, "Guardar", df_editor_data["ID Único"].isin(st.session_state.grupos_guardados))

                df_editado = st.data_editor(
                    df_editor_data,
                    use_container_width=True,
                    hide_index=True,
                    disabled=["ID Único", "Clave", "Asignatura", "Grupo", "Tipo", "Créditos", "Profesores", "Horarios"],
                    column_config={
                        "ID Único": None
                    },
                    key="editor_buscador"
                )

                if st.button("Actualizar mis grupos guardados", type="primary"):
                    seleccionados = set(df_editado[df_editado["Guardar"] == True]["ID Único"])
                    deseleccionados = set(df_editado[df_editado["Guardar"] == False]["ID Único"])

                    st.session_state.grupos_guardados.update(seleccionados)
                    st.session_state.grupos_guardados.difference_update(deseleccionados)

                    st.toast("Grupos guardados actualizados con éxito", icon="✅")
                    st.rerun()

    # --- VISTA 2: PREDICCIÓN DE CUPO ---
    elif vista_actual == "Predicción de cupo":
        st.subheader("Predicción de Cupo y Análisis de Horarios")

        # Indicador de estado de la base de datos en vivo de GitHub
        if not df_historico.empty:
            ultima_lectura = df_historico['Fecha_Hora_Extraccion'].max().strftime('%Y-%m-%d %H:%M:%S')
            st.caption(f"🟢 **Telemetría en vivo conectada** | Última lectura capturada: `{ultima_lectura}`")
        else:
            st.caption("🟡 **Conectando con el repositorio de datos...**")

        if not st.session_state.grupos_guardados:
            st.info("Aún no has guardado ningún grupo. Utiliza el **Buscador de Grupos** para seleccionar las materias de tu interés.")
        else:
            df_guardados = df_horarios[df_horarios["ID Único"].isin(st.session_state.grupos_guardados)].copy()
            cols_resumen = ["ID Único", "Clave", "Asignatura", "Grupo", "Tipo", "Profesores", "Horarios"]
            
            st.dataframe(df_guardados[cols_resumen], use_container_width=True, hide_index=True)

            st.divider()
            col_b1, col_b2 = st.columns([1, 4])
            with col_b1:
                if st.button("Limpiar todos los grupos", type="secondary"):
                    st.session_state.grupos_guardados.clear()
                    st.rerun()