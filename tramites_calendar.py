from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "Documentación"


def cargar_contenido_ics():
    """Lee el archivo .ics real alojado en el repositorio (21.6 KB / 694 líneas)."""
    posibles_rutas = [
        DOCS_DIR / "Calendar_Tramites_FQ.ics",
        DOCS_DIR / "Calendar_Tramites _FQ.ics",
        BASE_DIR / "Calendar_Tramites_FQ.ics",
        BASE_DIR / "Calendar_Tramites _FQ.ics",
    ]

    for ruta in posibles_rutas:
        if ruta.exists():
            with open(ruta, "r", encoding="utf-8") as f:
                return f.read()

    # Respaldo básico en caso de que no se encuentre el archivo local
    return "BEGIN:VCALENDAR\nVERSION:2.0\nX-WR-CALNAME:Tramites FQ\nEND:VCALENDAR"


def obtener_df_tramites():
    """Formatea la lista de trámites clave para desplegar en la tabla interactiva de Streamlit."""
    tramites = [
        {
            "Trámite / Evento": "Pago Anual Inscripción 2027-1",
            "Periodo / Fecha": "27 al 31 de Julio, 2026",
            "Detalles": "Entregar comprobante de pago en CAE",
        },
        {
            "Trámite / Evento": "Trámites obligatorios previos",
            "Periodo / Fecha": "28 al 31 de Julio, 2026",
            "Detalles": (
                "Evaluación docente, número de control y hoja de reinscripción"
            ),
        },
        {
            "Trámite / Evento": "Publicación de Horarios",
            "Periodo / Fecha": "29 de Julio, 2026",
            "Detalles": "Consulta de turnos e intensidades",
        },
        {
            "Trámite / Evento": "Solicitud Cambio de Carrera Interno",
            "Periodo / Fecha": "29 de Julio, 2026",
            "Detalles": "Trámite en portal de escolares",
        },
        {
            "Trámite / Evento": "Reinscripciones (Proceso General)",
            "Periodo / Fecha": "03 al 06 de Agosto, 2026",
            "Detalles": "Inscripción en línea según turno asignado",
        },
        {
            "Trámite / Evento": "Turnos de Artículo 22",
            "Periodo / Fecha": "05 de Agosto, 2026",
            "Detalles": "Horarios asignados por Art. 22",
        },
        {
            "Trámite / Evento": "Registro de Extra Largo (EL)",
            "Periodo / Fecha": "07 de Agosto, 2026",
            "Detalles": "Registro oficial de materias EL",
        },
        {
            "Trámite / Evento": "Inicio de Clases (Semestre 2027-1)",
            "Periodo / Fecha": "10 de Agosto, 2026",
            "Detalles": "Inicio oficial del ciclo escolar",
        },
        {
            "Trámite / Evento": "Periodo de Bajas",
            "Periodo / Fecha": "17 de Agosto, 2026",
            "Detalles": "Baja de asignaturas sin afectación",
        },
        {
            "Trámite / Evento": "Periodo de Altas 'A'",
            "Periodo / Fecha": "18 de Agosto, 2026",
            "Detalles": "Ajuste de grupo por cupos disponibles",
        },
        {
            "Trámite / Evento": "Periodo de Altas 'B'",
            "Periodo / Fecha": "19 de Agosto, 2026",
            "Detalles": "Segunda vuelta de altas de asignaturas",
        },
        {
            "Trámite / Evento": "Exámenes Ordinarios (1a Vuelta)",
            "Periodo / Fecha": "30 Nov al 05 Dic, 2026",
            "Detalles": "Evaluaciones finales primera vuelta",
        },
        {
            "Trámite / Evento": "Exámenes Ordinarios (2a Vuelta)",
            "Periodo / Fecha": "07 al 12 de Diciembre, 2026",
            "Detalles": "Evaluaciones finales segunda vuelta",
        },
        {
            "Trámite / Evento": "Vacaciones Administrativas",
            "Periodo / Fecha": "14 Dic 2026 al 02 Ene 2027",
            "Detalles": "Suspensión de labores escolares",
        },
    ]
    return pd.DataFrame(tramites)
