import os
import csv
from bs4 import BeautifulSoup
from datetime import datetime

def extraer_historial_cupos(ruta_html, ruta_csv):
    # ==========================================
    # 1. EXTRACCIÓN DE DATOS DEL HTML
    # ==========================================
    with open(ruta_html, 'r', encoding='utf-8') as file:
        html_content = file.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    registros_extraccion = []
    
    tbodys = soup.find_all('tbody', class_='divide-y divide-gray-200 bg-white')

    for tbody in tbodys:
        filas = tbody.find_all('tr', recursive=False)
        
        for fila in filas:
            celdas = fila.find_all('td', recursive=False)
            
            if len(celdas) >= 5:
                clave = celdas[0].get_text(strip=True)
                if not clave.isdigit(): 
                    continue 
                
                grupo = celdas[2].get_text(strip=True)
                tipo = celdas[3].get_text(strip=True)
                
                # Creación del ID Único (Ej: 0030-1-TEO)
                tipo_corto = "TEO" if "teor" in tipo.lower() else "LAB" if "lab" in tipo.lower() else tipo.upper()[:3]
                id_unico = f"{clave}-{grupo}-{tipo_corto}"
                
                # Cupo Disponible
                cupo = "0"
                celda_cupo = fila.find('td', class_=lambda c: c and 'bg-green-600' in c)
                if celda_cupo:
                    spans_cupo = celda_cupo.find_all('span')
                    if len(spans_cupo) >= 2:
                        cupo_texto = spans_cupo[1].get_text(strip=True)
                        cupo = cupo_texto.replace('%', '').strip()

                # Registro en formato largo (3 columnas fijas)
                registros_extraccion.append({
                    "id_unico": id_unico,
                    "Fecha_Hora_Extraccion": fecha_actual,
                    "cupo": cupo
                })

    # ==========================================
    # 2. ESCRITURA EN CSV (Modo Append 'a')
    # ==========================================
    archivo_existe = os.path.exists(ruta_csv)
    encabezados = ["id_unico", "Fecha_Hora_Extraccion", "cupo"]

    with open(ruta_csv, 'a', encoding='utf-8', newline='') as archivo_escritura:
        escritor = csv.DictWriter(archivo_escritura, fieldnames=encabezados)
        
        if not archivo_existe:
            escritor.writeheader()
            
        escritor.writerows(registros_extraccion)

    print(f"[{fecha_actual}] Extracción exitosa. Se añadieron {len(registros_extraccion)} registros al historial.")

# Ejecutar el proceso
extraer_historial_cupos('Documentación/datos_crudos.html', 'Documentación/matriz_cupos.csv')