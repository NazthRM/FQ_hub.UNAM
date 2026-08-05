import datetime
import re
import pandas as pd
from typing import Dict, List, Set, Tuple


def parsear_horario_cadena(horarios_str: str) -> List[Dict]:
    """Convierte cadenas de texto del tipo 'Lun 08:30 a 10:00 (204) | Mie 08:30 a 10:00 (204)'

    a estructuras de tiempo procesables.
    """
    dias_map = {
        "LUN": "Lun",
        "MAR": "Mar",
        "MIE": "Mie",
        "MIÉ": "Mie",
        "JUE": "Jue",
        "VIE": "Vie",
        "SAB": "Sab",
        "SÁB": "Sab",
    }
    slots = []
    if not horarios_str or horarios_str == "Sin horario asignado":
        return slots

    bloques = horarios_str.split("|")
    pattern = re.compile(
        r"([A-Za-aáéíóúÁÉÍÓÚ]+)\s+(\d{1,2}:\d{2})\s+a\s+(\d{1,2}:\d{2})"
    )

    for b in bloques:
        match = pattern.search(b.strip())
        if match:
            dia_raw = match.group(1).upper()[:3]
            dia = dias_map.get(dia_raw, dia_raw.title())
            h_ini = datetime.datetime.strptime(match.group(2), "%H:%M").time()
            h_fin = datetime.datetime.strptime(match.group(3), "%H:%M").time()
            slots.append({"dia": dia, "hora_inicio": h_ini, "hora_fin": h_fin})

    return slots


def hay_empalme(slot1: Dict, slot2: Dict) -> bool:
    """Valida si dos bloques de clase chocan en el mismo día y rango de horas."""
    if slot1["dia"] != slot2["dia"]:
        return False
    return max(slot1["hora_inicio"], slot2["hora_inicio"]) < min(
        slot1["hora_fin"], slot2["hora_fin"]
    )


def validar_restricciones_tiempo(
    slots: List[Dict],
    hora_min_inicio: datetime.time = None,
    hora_max_fin: datetime.time = None,
    bloques_reservados: List[Dict] = None,
) -> bool:
    """Comprueba que una lista de slots respete los límites de horario y bloques reservados."""
    for s in slots:
        if hora_min_inicio and s["hora_inicio"] < hora_min_inicio:
            return False
        if hora_max_fin and s["hora_fin"] > hora_max_fin:
            return False

        if bloques_reservados:
            for b_res in bloques_reservados:
                if hay_empalme(s, b_res):
                    return False
    return True


def generar_combinaciones_horarios(
    configuracion_materias,
    df_horarios,
    grupos_guardados_set=None,
    hora_min_inicio=None,
    hora_max_fin=None,
    bloques_reservados=None,
    profesores_vetados=None,
    solo_disponibles: bool = True,
    max_resultados: int = 15,
):
    """Generador principal mediante Backtracking para encontrar combinaciones de horarios válidos."""
    if profesores_vetados is None:
        profesores_vetados = []
    if bloques_reservados is None:
        bloques_reservados = []

    # 1. APLICAR VETO DE PROFESORES
    def tiene_vetado(prof_str):
        if pd.isna(prof_str):
            return False
        for vetado in profesores_vetados:
            if vetado.lower() in str(prof_str).lower():
                return True
        return False

    df_filtrado = df_horarios[~df_horarios["Profesores"].apply(tiene_vetado)].copy()

    # 2. FILTRAR GRUPOS SIN CUPO EN VIVO
    if solo_disponibles and "Cupo Actual" in df_filtrado.columns:

        def tiene_cupo_disponible(cupo_str):
            if pd.isna(cupo_str):
                return True
            val_limpio = str(cupo_str).replace("%", "").strip()
            try:
                return float(val_limpio) > 0.0
            except ValueError:
                return True

        df_filtrado = df_filtrado[
            df_filtrado["Cupo Actual"].apply(tiene_cupo_disponible)
        ]

    # 3. SISTEMA DE CUBETAS DIRIGIDO POR EL USUARIO (TEORÍA / LAB)
    grupos_por_materia = []

    for config in configuracion_materias:
        asig = config["asignatura"]
        tipos_requeridos = config["tipos"]

        for tipo in tipos_requeridos:
            df_asig_tipo = df_filtrado[
                (df_filtrado["Asignatura"] == asig) & (df_filtrado["Tipo"] == tipo)
            ]
            grupos_tipo = df_asig_tipo.to_dict("records")

            if grupos_tipo:
                grupos_por_materia.append(grupos_tipo)
            else:
                # Si una materia/tipo no tiene grupos disponibles (por vetos o filtros), no hay combinación posible
                return []

    if not grupos_por_materia:
        return []

    soluciones_validas = []

    def backtracking(index: int, combinacion_actual: List[Dict]):
        if len(soluciones_validas) >= max_resultados * 3:
            return

        if index == len(grupos_por_materia):
            soluciones_validas.append(list(combinacion_actual))
            return

        for grupo in grupos_por_materia[index]:
            slots_grupo = parsear_horario_cadena(grupo.get("Horarios", ""))

            # 1. Validar filtros de horas límites y bloques reservados
            if not validar_restricciones_tiempo(
                slots_grupo,
                hora_min_inicio,
                hora_max_fin,
                bloques_reservados,
            ):
                continue

            # 2. Validar anti-empalme con la combinación ya elegida
            conflicto = False
            for g_elegido in combinacion_actual:
                slots_elegido = parsear_horario_cadena(g_elegido.get("Horarios", ""))
                for s1 in slots_grupo:
                    for s2 in slots_elegido:
                        if hay_empalme(s1, s2):
                            conflicto = True
                            break
                    if conflicto:
                        break
                if conflicto:
                    break

            if not conflicto:
                combinacion_actual.append(grupo)
                backtracking(index + 1, combinacion_actual)
                combinacion_actual.pop()

    backtracking(0, [])

    # Ponderación y Ranking de Soluciones
    resultados_evaluados = []
    for comb in soluciones_validas:
        # Puntuación por inclusión de grupos preferidos (guardados)
        grupos_ids = {g["ID Único"] for g in comb}
        bonificacion_guardados = (
            len(grupos_ids.intersection(grupos_guardados_set)) * 15.0
        )

        # Cálculo de compactación (minimizar huecos)
        puntuacion_total = 100.0 + bonificacion_guardados

        resultados_evaluados.append(
            {
                "combinacion": comb,
                "score_compatibilidad": puntuacion_total,
                "grupos_guardados_incluidos": len(
                    grupos_ids.intersection(grupos_guardados_set)
                ),
            }
        )

    # Ordenar por el mejor Score
    resultados_evaluados.sort(key=lambda x: x["score_compatibilidad"], reverse=True)
    return resultados_evaluados[:max_resultados]
