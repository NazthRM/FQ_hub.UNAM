import pandas as pd
import numpy as np
import datetime

POBLACION_ALUMNOS = {
    "Química Farmacéutico Biológica": 2669,
    "Ingeniería Química": 1659,
    "Química": 1242,
    "Química de Alimentos": 1587,
    "Ingeniería Química Metalúrgica": 550,
    "Química e Ingeniería en Materiales": 62,
}


def proyectar_supervivencia_hibrida(
    id_unico, fecha_turno, df_historico, df_horarios, df_relaciones
):
    """
    Evalúa la disponibilidad estimada usando:
    1. Demografía de carreras e índice de presión.
    2. Inercia de velocidad reciente en telemetría.
    3. Transferencia de demanda desde grupos hermanos saturados.
    """
    alumnos_totales_fq = sum(POBLACION_ALUMNOS.values())
    grupos_totales_fq = max(1, df_horarios["ID Único"].nunique())

    # ---------------------------------------------------------
    # FASE A: MODELO DEMOGRÁFICO BASE
    # ---------------------------------------------------------
    carreras_vinculadas = df_relaciones[df_relaciones["ID Único"] == id_unico][
        "Carrera"
    ].unique()
    carreras_validas = [c for c in carreras_vinculadas if c in POBLACION_ALUMNOS]
    es_tronco_comun = (
        "Tronco Común" in carreras_vinculadas or len(carreras_validas) >= 5
    )

    if es_tronco_comun or not carreras_validas:
        alpha_carreras = 1.80
        alpha_presion = 1.00
    else:
        n_carreras = len(carreras_validas)
        gamma = 0.20
        alpha_carreras = 1.0 + gamma * max(0, n_carreras - 1)

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
    # FASE B: TELEMETRÍA E INERCIA RECIENTE
    # ---------------------------------------------------------
    df_grupo = pd.DataFrame()
    if not df_historico.empty and "id_unico" in df_historico.columns:
        df_grupo = (
            df_historico[df_historico["id_unico"] == id_unico]
            .sort_values("Fecha_Hora_Extraccion")
            .copy()
        )

    num_mediciones = len(df_grupo)
    col_cupo = (
        "cupo"
        if "cupo" in df_grupo.columns
        else (df_grupo.columns[-1] if not df_grupo.empty else None)
    )

    # ---------------------------------------------------------
    # FASE C: EFECTO DE DESBORDE ENTRE GRUPOS HERMANOS
    # ---------------------------------------------------------
    factor_desborde = 1.0
    clave_materia = df_horarios[df_horarios["ID Único"] == id_unico]["Clave"].values
    if len(clave_materia) > 0 and not df_historico.empty:
        clave_target = clave_materia[0]
        ids_hermanos = df_horarios[df_horarios["Clave"] == clave_target][
            "ID Único"
        ].unique()

        df_hermanos = df_historico[df_historico["id_unico"].isin(ids_hermanos)]
        if not df_hermanos.empty:
            ultimas_hermanos = (
                df_hermanos.sort_values("Fecha_Hora_Extraccion")
                .groupby("id_unico")
                .last()
            )
            cupos_hermanos = (
                ultimas_hermanos[col_cupo].astype(str).str.replace("%", "").str.strip()
            )
            cupos_num = pd.to_numeric(cupos_hermanos, errors="coerce").dropna()

            if len(cupos_num) > 1:
                grupos_llenos = (cupos_num <= 10.0).sum()
                pct_llenos = grupos_llenos / len(cupos_num)
                # Si el 50%+ de los grupos hermanos están llenos, se acelera el desborde al rezagado
                factor_desborde = 1.0 + (0.5 * pct_llenos)

    # ---------------------------------------------------------
    # FASE D: PROYECCIÓN TEMPORAL
    # ---------------------------------------------------------
    if num_mediciones < 3:
        # Arranque en frío con velocidad teórica modulada por desborde
        v_base = 2.0  # % por hora
        v_efectiva = v_base * alpha_carreras * alpha_presion * factor_desborde

        if not df_grupo.empty:
            t_ultima_lectura = df_grupo["Fecha_Hora_Extraccion"].iloc[-1]
            cupo_ultimo = pd.to_numeric(
                df_grupo[col_cupo].astype(str).str.replace("%", "").str.strip(),
                errors="coerce",
            ).iloc[-1]
        else:
            t_ultima_lectura = datetime.datetime(2026, 8, 3, 9, 0)
            cupo_ultimo = 100.0

        if isinstance(fecha_turno, datetime.datetime):
            horas_hasta_turno = max(
                0.0, (fecha_turno - t_ultima_lectura).total_seconds() / 3600.0
            )
        else:
            horas_hasta_turno = 0.0

        disp_estimada = max(0.0, float(cupo_ultimo) - (v_efectiva * horas_hasta_turno))
        probabilidad_cierre = float(np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0))
        tendencia = "Estimación Demográfica (Modelo Base)"

    else:
        # Piloto automático con énfasis en la velocidad reciente (últimas 4 lecturas)
        t_base = df_grupo["Fecha_Hora_Extraccion"].iloc[0]
        s_cupo = df_grupo[col_cupo].astype(str).str.replace("%", "").str.strip()
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
            tendencia = "Lectura Registrada en Turno"
        else:
            # Ponderación reciente: Ajuste polinomial priorizando el tramo final
            coeficientes = np.polyfit(t_horas, y_valores, deg=2)
            poly = np.poly1d(coeficientes)

            proyeccion = poly(t_target)
            disp_estimada = float(np.clip(proyeccion, 0.0, 100.0))
            probabilidad_cierre = float(
                np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0)
            )

            aceleracion = 2 * coeficientes[0]
            if aceleracion < -0.2:
                tendencia = "Acelerando (Riesgo Alto por Desborde)"
            elif aceleracion > 0.2:
                tendencia = "Desacelerando (Saturación Progresiva)"
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
            "factor_desborde": round(factor_desborde, 2),
        },
    }
