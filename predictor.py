import pandas as pd
import numpy as np
import datetime

# ==========================================
# 1. POBLACIÓN ESTUDIANTIL ESTIMADA (Censo)
# ==========================================
POBLACION_ALUMNOS = {
    "Química Farmacéutico Biológica": 2669,
    "Ingeniería Química": 1659,
    "Química": 1242,
    "Química de Alimentos": 1587,
    "Ingeniería Química Metalúrgica": 550,
    "Química e Ingeniería en Materiales": 62,
}


# ==========================================
# 2. MOTOR HÍBRIDO DE PREDICCIÓN DE CUPO
# ==========================================
def proyectar_supervivencia_hibrida(
    id_unico, fecha_turno, df_historico, df_horarios, df_relaciones
):
    """
    Evalúa la disponibilidad (0.0% a 100.0%) de un grupo fusionando factores
    demográficos/multicarrera (teoría) con regresión cinemática (telemetría en vivo).
    """
    # Suma dinámica de la población total de la facultad
    alumnos_totales_fq = sum(POBLACION_ALUMNOS.values())
    grupos_totales_fq = max(1, df_horarios["ID Único"].nunique())

    # ---------------------------------------------------------
    # FASE A: FACTORES TEÓRICOS (Agotamiento Efectivo)
    # ---------------------------------------------------------
    carreras_vinculadas = df_relaciones[df_relaciones["ID Único"] == id_unico][
        "Carrera"
    ].unique()

    carreras_validas = [c for c in carreras_vinculadas if c in POBLACION_ALUMNOS]
    es_tronco_comun = (
        "Tronco Común" in carreras_vinculadas or len(carreras_validas) >= 5
    )

    if es_tronco_comun or not carreras_validas:
        # Asignaturas de Tronco Común: Máxima competencia cruzada entre todas las carreras
        alpha_carreras = 1.80
        alpha_presion = 1.00
    else:
        # Factor Multicarrera
        n_carreras = len(carreras_validas)
        gamma = 0.20
        alpha_carreras = 1.0 + gamma * max(0, n_carreras - 1)

        # Factor Presión Demográfica
        p_totales = []
        for c in carreras_validas:
            alumnos_c = POBLACION_ALUMNOS[c]
            grupos_c = max(
                1, df_relaciones[df_relaciones["Carrera"] == c]["ID Único"].nunique()
            )

            prop_alumnos = alumnos_c / alumnos_totales_fq
            prop_grupos = grupos_c / grupos_totales_fq

            p_c = prop_alumnos / prop_grupos if prop_grupos > 0 else 1.0
            p_totales.append(p_c)

        alpha_presion = float(np.mean(p_totales)) if p_totales else 1.0

    # ---------------------------------------------------------
    # FASE B: EVALUACIÓN DE TELEMETRÍA (Cinemática / Histórico)
    # ---------------------------------------------------------
    df_grupo = pd.DataFrame()
    if not df_historico.empty and "id_unico" in df_historico.columns:
        df_grupo = (
            df_historico[df_historico["id_unico"] == id_unico]
            .sort_values("Fecha_Hora_Extraccion")
            .copy()
        )

    num_mediciones = len(df_grupo)

    columna_cupo = (
        "cupo"
        if "cupo" in df_grupo.columns
        else (df_grupo.columns[-1] if not df_grupo.empty else None)
    )

    if num_mediciones < 3:
        # -----------------------------------------------------
        # FASE 1: ARRANQUE EN FRÍO (Teórico / Demográfico)
        # -----------------------------------------------------
        v_base = 2.0  # Decaimiento nominal del porcentaje por hora
        v_efectiva = v_base * alpha_carreras * alpha_presion

        ahora = datetime.datetime.now()
        if isinstance(fecha_turno, datetime.datetime):
            horas_restantes = max(0.0, (fecha_turno - ahora).total_seconds() / 3600.0)
        else:
            horas_restantes = 12.0

        disp_estimada = max(0.0, 100.0 - (v_efectiva * horas_restantes))
        probabilidad_cierre = float(np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0))
        tendencia = "Estimación Teórica (Faltan datos en vivo)"

    else:
        # -----------------------------------------------------
        # FASE 2: PILOTO AUTOMÁTICO (Regresión Polinomial)
        # -----------------------------------------------------
        t_base = df_grupo["Fecha_Hora_Extraccion"].iloc[0]

        s_cupo = df_grupo[columna_cupo].astype(str).str.replace("%", "").str.strip()
        df_grupo["y_porcentaje"] = pd.to_numeric(s_cupo, errors="coerce").fillna(100.0)

        t_horas = (
            df_grupo["Fecha_Hora_Extraccion"] - t_base
        ).dt.total_seconds() / 3600.0
        y_valores = df_grupo["y_porcentaje"].values

        if isinstance(fecha_turno, datetime.datetime):
            t_target = (fecha_turno - t_base).total_seconds() / 3600.0
        else:
            t_target = t_horas.iloc[-1]

        if t_target <= t_horas.iloc[-1]:
            disp_estimada = float(y_valores[-1])
            probabilidad_cierre = float(
                np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0)
            )
            tendencia = "Estática (Turno actual/pasado)"
        else:
            coeficientes = np.polyfit(t_horas, y_valores, deg=2)
            poly = np.poly1d(coeficientes)

            proyeccion = poly(t_target)
            disp_estimada = float(np.clip(proyeccion, 0.0, 100.0))
            probabilidad_cierre = float(
                np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0)
            )

            aceleracion = 2 * coeficientes[0]
            if aceleracion < -0.2:
                tendencia = "Acelerando (Riesgo Alto de Cierre)"
            elif aceleracion > 0.2:
                tendencia = "Desacelerando (Estabilización por Saturación)"
            else:
                tendencia = "Consumo Constante"

    return {
        "disponibilidad_estimada_pct": round(disp_estimada, 1),
        "probabilidad_cierre": round(probabilidad_cierre, 2),
        "tendencia": tendencia,
        "mediciones_usadas": num_mediciones,
        "factores": {
            "alpha_carreras": round(alpha_carreras, 2),
            "alpha_presion": round(alpha_presion, 2),
        },
    }
