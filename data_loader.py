import datetime
import numpy as np
import pandas as pd

POBLACION_ALUMNOS = {
    "Química Farmacéutico Biológica": 2669,
    "Ingeniería Química": 1659,
    "Química": 1242,
    "Química de Alimentos": 1587,
    "Ingeniería Química Metalúrgica": 550,
    "Química e Ingeniería en Materiales": 62,
}


def calcular_horas_activas_inscripcion(
    t_inicio: datetime.datetime, t_fin: datetime.datetime
) -> float:
    """Calcula las horas transcurridas considerando ÚNICAMENTE el horario activo (09:00 a 19:00 hrs CDMX).

    Descuenta las 14 horas nocturnas para no aplanar la pendiente de
    agotamiento.
    """
    if t_inicio >= t_fin:
        return 0.0

    HORA_INICIO = 9
    HORA_FIN = 19
    total_segundos = 0.0
    curr = t_inicio

    while curr < t_fin:
        inicio_dia_activo = curr.replace(
            hour=HORA_INICIO, minute=0, second=0, microsecond=0
        )
        fin_dia_activo = curr.replace(hour=HORA_FIN, minute=0, second=0, microsecond=0)

        tramo_inicio = max(curr, inicio_dia_activo)
        tramo_fin = min(t_fin, fin_dia_activo)

        if tramo_inicio < tramo_fin:
            total_segundos += (tramo_fin - tramo_inicio).total_seconds()

        # Avanzar al inicio de la jornada del día siguiente
        sig_dia = curr.date() + datetime.timedelta(days=1)
        curr = datetime.datetime.combine(sig_dia, datetime.time(HORA_INICIO, 0))

    return total_segundos / 3600.0


def proyectar_supervivencia_hibrida(
    id_unico, fecha_turno, df_historico, df_horarios, df_relaciones
):
    """Evalúa la disponibilidad estimada garantizando monotonía y tiempo activo de inscripción."""
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
                1,
                df_relaciones[df_relaciones["Carrera"] == c]["ID Único"].nunique(),
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
                factor_desborde = 1.0 + (0.5 * pct_llenos)

    # ---------------------------------------------------------
    # FASE D: PROYECCIÓN TEMPORAL CON TIEMPO ACTIVO
    # ---------------------------------------------------------
    cupo_ultimo_registrado = 100.0
    if not df_grupo.empty and col_cupo:
        s_cupo_last = str(df_grupo[col_cupo].iloc[-1]).replace("%", "").strip()
        cupo_ultimo_registrado = float(
            pd.to_numeric(s_cupo_last, errors="coerce") or 0.0
        )

    if cupo_ultimo_registrado <= 0.0:
        return {
            "disponibilidad_estimada_pct": 0.0,
            "probabilidad_cierre": 1.0,
            "tendencia": "Grupo Agotado (Lleno Total)",
            "mediciones_usadas": num_mediciones,
            "factores": {
                "alpha_carreras": round(alpha_carreras, 2),
                "alpha_presion": round(alpha_presion, 2),
                "factor_desborde": round(factor_desborde, 2),
            },
        }

    if num_mediciones < 3:
        v_base = 2.0  # % por hora activa
        v_efectiva = v_base * alpha_carreras * alpha_presion * factor_desborde

        t_ultima_lectura = (
            df_grupo["Fecha_Hora_Extraccion"].iloc[-1]
            if not df_grupo.empty
            else datetime.datetime(2026, 8, 3, 9, 0)
        )

        if isinstance(fecha_turno, datetime.datetime):
            horas_activas = calcular_horas_activas_inscripcion(
                t_ultima_lectura, fecha_turno
            )
        else:
            horas_activas = 0.0

        proyeccion_raw = cupo_ultimo_registrado - (v_efectiva * horas_activas)
        disp_estimada = float(np.clip(proyeccion_raw, 0.0, cupo_ultimo_registrado))
        probabilidad_cierre = float(np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0))
        tendencia = "Estimación Demográfica (Modelo Base)"

    else:
        t_base = df_grupo["Fecha_Hora_Extraccion"].iloc[0]
        s_cupo = df_grupo[col_cupo].astype(str).str.replace("%", "").str.strip()
        df_grupo["y_porcentaje"] = pd.to_numeric(s_cupo, errors="coerce").fillna(100.0)

        # Matriz de horas activas transcurridas
        t_horas_activas = [
            calcular_horas_activas_inscripcion(t_base, t)
            for t in df_grupo["Fecha_Hora_Extraccion"]
        ]
        y_valores = df_grupo["y_porcentaje"].values

        if isinstance(fecha_turno, datetime.datetime):
            t_target = calcular_horas_activas_inscripcion(t_base, fecha_turno)
        else:
            t_target = t_horas_activas[-1]

        if t_target <= t_horas_activas[-1]:
            disp_estimada = float(y_valores[-1])
            probabilidad_cierre = float(
                np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0)
            )
            tendencia = "Lectura Registrada en Turno"
        else:
            coeficientes = np.polyfit(t_horas_activas, y_valores, deg=2)
            poly = np.poly1d(coeficientes)

            proyeccion_raw = poly(t_target)
            disp_estimada = float(np.clip(proyeccion_raw, 0.0, cupo_ultimo_registrado))
            probabilidad_cierre = float(
                np.clip(1.0 - (disp_estimada / 100.0), 0.0, 1.0)
            )

            aceleracion = 2 * coeficientes[0]
            if disp_estimada <= 0.0:
                tendencia = "Grupo Agotado (Lleno Total)"
            elif aceleracion < -0.2:
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

        # Identificar si ya llegó a 0% y a qué hora
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
