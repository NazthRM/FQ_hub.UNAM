import pandas as pd
import json
import os
import streamlit as st

# URL Raw de GitHub para la matriz de cupos en vivo
URL_RAW_CUPOS = "https://raw.githubusercontent.com/NazthRM/rastreocuposfq/main/Documentaci%C3%B3n/matriz_cupos.csv"

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

        # Tabla base de materias/grupos[cite: 8]
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

            # Normalización basada ÚNICAMENTE en el campo 'caracter' del JSON[cite: 8]
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

@st.cache_data(ttl=300) # Se refresca automáticamente cada 5 minutos[cite: 8]
def cargar_historico_en_vivo():
    try:
        # Leer directamente del Raw de GitHub[cite: 8]
        df_live = pd.read_csv(URL_RAW_CUPOS)
        df_live["Fecha_Hora_Extraccion"] = pd.to_datetime(df_live["Fecha_Hora_Extraccion"])
        
        # PARCHE DINÁMICO (Línea base del 3 de agosto)[cite: 8]
        es_hoy_madrugada = (df_live["Fecha_Hora_Extraccion"].dt.date == pd.to_datetime("2026-08-03").date()) & \
                           (df_live["Fecha_Hora_Extraccion"].dt.hour < 9)
        
        df_live.loc[es_hoy_madrugada, "Fecha_Hora_Extraccion"] = pd.to_datetime("2026-08-03 09:00:00")
        
        # Ordenar cronológicamente para cálculos de regresión[cite: 8]
        df_live = df_live.sort_values(by=["id_unico", "Fecha_Hora_Extraccion"])
        
        return df_live
    except Exception as e:
        return pd.DataFrame()