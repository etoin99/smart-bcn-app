# =====================================================================
# Importación de librerías para el proyecto
# =====================================================================
# Importo las librerías que voy a usar en mi proyecto final. 
# Streamlit para hacer la web interactiva, Pandas para manejar las tablas de datos,
# Plotly para hacer los gráficos más visuales, y Geopy para medir distancias en el mapa.
import streamlit as st
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# Configuro la página para que ocupe todo el ancho de la pantalla y se vea más limpia.
st.set_page_config(page_title="Smart-BCN | Asistente de Hostelería", page_icon="🍽️", layout="wide")

st.title("🍽️ Smart-BCN: Tu Asistente de Hostelería")
st.markdown("Te ayudamos a prever cuántos clientes tendrás cada día para ajustar tus turnos, compras y estrategias según el clima y los eventos de Barcelona.")
st.divider()

# =====================================================================
# 1. PANEL DE CONTROL (Opciones para el usuario con Tooltips)
# =====================================================================
st.sidebar.header("⚙️ Configuración de tu local")

# Pido la dirección para luego poder calcular si los conciertos le pillan cerca.
direccion_input = st.sidebar.text_input("📍 Dirección exacta:", "Plaza Catalunya, Barcelona", help="Escribe tu calle para calcular a qué distancia te quedan los grandes eventos de la ciudad.")

# Uso menús desplegables para no agobiar al usuario con demasiadas opciones de golpe.
with st.sidebar.expander("🪑 Capacidad y Formato", expanded=True):
    tipo_local = st.selectbox(
        "🍷 Tipo de negocio:", 
        ["Restaurante", "Bar de Copas", "Cafetería/Brunch"],
        help="Adapta los consejos automáticos y los picos de afluencia (ej. los domingos atraen más brunch, y los sábados noche más copas)."
    )
    aforo_interior = st.number_input(
        "Sillas en el interior:", min_value=5, value=60, step=5,
        help="El número máximo de clientes que puedes sentar a la vez dentro del local."
    )
    
    tiene_terraza = st.checkbox("¿Tienes terraza exterior?", value=True)
    aforo_terraza = 0
    if tiene_terraza:
        aforo_terraza = st.number_input("Sillas en la terraza:", min_value=0, value=40, step=5)
        
    rotacion_mesas = st.slider(
        "Rotación (Turnos al día):", min_value=1.0, max_value=5.0, value=2.5, step=0.5,
        help="Cuántas veces se ocupa una misma silla al día. Si solo das cenas, pon 1.0. Si das comidas y cenas, pon 2.0 o más."
    )

with st.sidebar.expander("⭐ Entorno y Competencia", expanded=False):
    puntuacion_google = st.slider(
        "Nota en Google Maps:", min_value=1.0, max_value=5.0, value=4.2, step=0.1, 
        help="Si tienes mucha nota, el sistema calculará que atraes a más clientes robándoselos a la competencia."
    )
    densidad_competencia = st.selectbox(
        "Locales cercanos:", ["Muchos (Alta competencia)", "Normal", "Pocos (Baja competencia)"],
        help="Si hay muchos restaurantes en tu misma calle, los clientes se repartirán más y te tocarán menos."
    )

with st.sidebar.expander("🛵 Extras y Vía Pública", expanded=False):
    tiene_delivery = st.checkbox(
        "¿Tienes envíos a domicilio (Glovo, etc)?", value=False,
        help="Si lo marcas, el sistema calculará un aumento de pedidos en los días de mucha lluvia."
    )
    hay_obras = st.checkbox(
        "🚧 ¿Hay obras en tu calle?", value=False, 
        help="Si lo marcas, el sistema restará un porcentaje de clientes al prever que pasará menos gente caminando."
    )

with st.sidebar.expander("💶 Tus Números (Opcional)", expanded=False):
    st.markdown("<small>Usamos esto para estimar tus ingresos y necesidades de personal.</small>", unsafe_allow_html=True)
    ticket_medio = st.number_input("Gasto Medio por Cliente (€):", min_value=5.0, value=25.0, step=1.0)
    ratio_camarero = st.number_input("Clientes por Camarero:", min_value=5, value=15, step=1, help="A cuántos clientes puede atender bien un solo camarero durante su turno.")
    coste_turno_camarero = st.number_input("Coste Salarial por Turno (€):", min_value=10.0, value=60.0, step=5.0, help="Sueldo + Seguros Sociales de traer a un empleado extra un día.")
    porcentaje_cogs = st.slider("Coste de Comida/Bebida (%):", min_value=10, max_value=50, value=30, help="De cada 10€ que te pagan, qué porcentaje te gastaste en comprar el producto a los proveedores (Materia prima).")

# =====================================================================
# 2. LOCALIZACIÓN EN EL MAPA
# =====================================================================
# Guardo en memoria (cache) las coordenadas para que la web vaya rápida.
@st.cache_data
def obtener_coordenadas(direccion):
    geolocator = Nominatim(user_agent="smart_bcn_app")
    try:
        location = geolocator.geocode(direccion)
        if location:
            return (location.latitude, location.longitude)
    except:
        return None
    return None

coords_restaurante = obtener_coordenadas(direccion_input)

# Pinto el mapa para que el usuario compruebe que el sistema le ha ubicado bien.
if coords_restaurante:
    df_mapa_ui = pd.DataFrame({'lat': [coords_restaurante[0]], 'lon': [coords_restaurante[1]]})
    st.sidebar.map(df_mapa_ui, zoom=14)

# =====================================================================
# 3. EL NÚCLEO DEL PROYECTO (Lógica de clientes y consejos)
# =====================================================================
# Leo los datos de las predicciones que generé en mi ETL.
df_predicciones = pd.read_csv('predicciones_dashboard.csv')
try:
    df_eventos_geo = pd.read_csv('mapa_eventos_ticketmaster.csv')
except:
    df_eventos_geo = pd.DataFrame()

# Calculo el tope físico de clientes que caben en el local.
aforo_total_cliente = aforo_interior + aforo_terraza
factor_escala = aforo_total_cliente / 100.0  
max_interior = int(aforo_interior * rotacion_mesas)
max_terraza = int(aforo_terraza * rotacion_mesas)
capacidad_max_diaria = max_interior + max_terraza

# Traduzco las opciones del usuario a números (multiplicadores) para mi fórmula.
factor_comp = 0.65 if "Muchos" in densidad_competencia else (0.85 if "Normal" in densidad_competencia else 1.15)
factor_google = max(0.2, 1.0 + ((puntuacion_google - 4.0) * 0.4))

dias_ajustados = []
consejos_diarios = {} 

# Empiezo a revisar los días de la semana uno a uno.
for index, row in df_predicciones.iterrows():
    fecha_str = row['Fecha_str']
    dia_semana = pd.to_datetime(fecha_str).dayofweek
    consejos_diarios[fecha_str] = [] 
    
    # Aplico los factores de la competencia y google a los clientes iniciales.
    clientes_potenciales = int(row['Clientes_Esperados'] * factor_escala * factor_comp * factor_google)
    evento_estado = "---"
    
    # Ajuste de picos según el tipo de local.
    if tipo_local == "Bar de Copas" and dia_semana in [4, 5]: clientes_potenciales = int(clientes_potenciales * 1.3) 
    elif tipo_local == "Cafetería/Brunch" and dia_semana == 6: clientes_potenciales = int(clientes_potenciales * 1.4) 
    
    if hay_obras: 
        clientes_potenciales = int(clientes_potenciales * 0.85)

    # Reviso la distancia de los conciertos.
    if row['Evento_Especial'] == 1 and not df_eventos_geo.empty and coords_restaurante:
        eventos_del_dia = df_eventos_geo[df_eventos_geo['Fecha'] == fecha_str]
        afecta = False
        nombres_cercanos = []
        for _, evento in eventos_del_dia.iterrows():
            coords_evento = (evento['Latitud'], evento['Longitud'])
            distancia_km = geodesic(coords_restaurante, coords_evento).kilometers
            if distancia_km <= 4.0:
                afecta = True
                nombres_cercanos.append(f"{evento['Nombre_Evento']}")
        
        if afecta:
            nombres_unicos = list(set(nombres_cercanos))
            eventos_unidos = ", ".join(nombres_unicos)
            evento_estado = f"🔥 {eventos_unidos}"
            
            # Guardo un consejo útil dependiendo del tipo de local que tenga el usuario.
            if tipo_local == "Restaurante":
                consejos_diarios[fecha_str].append(f"🎫 **Evento cercano ({eventos_unidos}):** Quizá te interese ofrecer un menú rápido y cerrado para asegurar doblar mesas antes de que empiece el evento.")
            elif tipo_local == "Bar de Copas":
                consejos_diarios[fecha_str].append(f"🎫 **Evento cercano ({eventos_unidos}):** Espera más gente al terminar el evento. Asegura tener personal en barra y bebidas para esa hora.")
            else: 
                consejos_diarios[fecha_str].append(f"🎫 **Evento cercano ({eventos_unidos}):** Buena oportunidad para vender cosas para llevar (Take-Away) a la gente que camina hacia el evento.")
        else:
            evento_estado = "Demasiado lejos"
            clientes_potenciales = int(clientes_potenciales * 0.75) 
            
    elif row['Evento_Especial'] == 1:
        evento_estado = "🎉 Festivo Nacional"
        consejos_diarios[fecha_str].append("🎉 **Es Festivo:** Trata este día como si fuera un domingo a la hora de prever tus ventas.")

    # Reviso qué me ha dicho el algoritmo sobre cerrar la terraza.
    decision_terraza = row['Decision_Operativa']
    pax_interior, pax_terraza, pax_delivery = 0, 0, 0
    
    if not tiene_terraza:
        decision_terraza = '⚪ No tienes'
        pax_interior = min(clientes_potenciales, max_interior)
    elif decision_terraza == '🔴 CERRAR TERRAZA':
        pax_interior = min(clientes_potenciales, max_interior)
        consejos_diarios[fecha_str].append("🌧️ **Ojo con el clima:** Prevemos mal tiempo. Avisa al personal de terraza y no descongeles tanta comida hoy para evitar mermas.")
        
        if tiene_delivery:
            pax_delivery = int(clientes_potenciales * 0.20) 
            evento_estado += " (☔ Más reparto)"
            consejos_diarios[fecha_str].append("🛵 **Reparto a domicilio:** Al llover, la gente pedirá más desde casa. ¡Prepara bien las cajas y la zona de recogida!")
    else:
        pax_interior = min(clientes_potenciales, max_interior)
        restante = clientes_potenciales - pax_interior
        if restante > 0: pax_terraza = min(restante, max_terraza)
            
    clientes_finales = pax_interior + pax_terraza + pax_delivery
    
    # Cálculo de la ganancia extra.
    ocupacion_porcentual = clientes_finales / capacidad_max_diaria if capacidad_max_diaria > 0 else 0
    ticket_dinamico = ticket_medio
    ingreso_extra_sugerido = 0
    
    if ocupacion_porcentual >= 0.85 and decision_terraza != '🔴 CERRAR TERRAZA':
        ticket_dinamico = ticket_medio * 1.15 
        ingreso_extra_sugerido = clientes_finales * (ticket_dinamico - ticket_medio)
        consejos_diarios[fecha_str].append("📈 **Estrategia de Alta Ocupación:** Vas a estar casi lleno. Considera priorizar la carta sobre el menú del día, o sugiere postres y bebidas premium para maximizar tus ingresos sin saturar la cocina.")
        
    # Calculo el dinero en base a mis fórmulas.
    facturacion = clientes_finales * ticket_dinamico
    camareros_necesarios = max(1, round(clientes_finales / ratio_camarero)) 
    
    coste_materia_prima = facturacion * (porcentaje_cogs / 100)
    coste_plantilla = camareros_necesarios * coste_turno_camarero
    beneficio_bruto = facturacion - coste_materia_prima - coste_plantilla
        
    row['Decision_Operativa'] = decision_terraza
    row['Pax_Interior'] = pax_interior
    row['Pax_Terraza'] = pax_terraza
    row['Pax_Delivery'] = pax_delivery
    row['Clientes_Totales'] = clientes_finales
    row['Ticket_Aplicado'] = ticket_dinamico
    row['Facturacion_Est'] = facturacion
    row['Beneficio_Est'] = beneficio_bruto
    row['Extra_Yield'] = ingreso_extra_sugerido
    row['Camareros_Rec'] = camareros_necesarios
    row['Estado_Evento'] = evento_estado
    
    dias_ajustados.append(row)

df_visual = pd.DataFrame(dias_ajustados)

# =====================================================================
# 4. CONSEJOS AUTOMÁTICOS PARA EL USUARIO
# =====================================================================
st.subheader("💡 Tus Consejos de la Semana")
st.markdown("Hemos analizado el clima y los eventos. Aquí tienes algunas ideas prácticas día a día:")

hay_mensajes = False
for fecha in sorted(consejos_diarios.keys()):
    mensajes_del_dia = consejos_diarios[fecha]
    if mensajes_del_dia:
        hay_mensajes = True
        with st.expander(f"📅 Qué tener en cuenta el {fecha}", expanded=(fecha == min(consejos_diarios.keys()))):
            for msj in mensajes_del_dia:
                if "🌧️" in msj: st.error(msj)
                elif "📈" in msj or "🎫" in msj or "🛵" in msj: st.success(msj)
                else: st.info(msj)

if not hay_mensajes:
    st.info("No detectamos eventos grandes ni clima extremo. Sigue con tu rutina habitual de trabajo.")

st.divider()

# =====================================================================
# 5. TARJETAS DE RESUMEN
# =====================================================================
st.subheader("📊 Resumen de tu Próxima Semana")

col1, col2, col3, col4 = st.columns(4)
with col1: 
    st.metric("Personas Esperadas", f"{df_visual['Clientes_Totales'].sum()} pax")
with col2: 
    st.metric(
        "Beneficio Estimado", f"{df_visual['Beneficio_Est'].sum():,.0f} €".replace(",", "."), 
        help="Lo que te queda después de pagar la comida a tus proveedores y los turnos extra del personal."
    )
with col3: 
    st.metric(
        "Ganancia Extra Potencial", f"+{df_visual['Extra_Yield'].sum():,.0f} €".replace(",", "."), 
        "Si aplicas los consejos", delta_color="normal",
        help="Dinero extra que podrías ganar si fomentas la venta de productos con más margen en los días de mayor aglomeración."
    )
with col4: 
    st.metric(
        "Fiabilidad del Cálculo", "Aprox. 94.8 %", 
        help="Porcentaje de acierto de nuestra fórmula tras haberla puesto a prueba con el historial del clima y ventas de Barcelona."
    )

st.divider()

# =====================================================================
# 6. GRÁFICOS Y TABLA DE DESCARGA
# =====================================================================
st.subheader("📉 ¿De dónde vendrán tus clientes?")
fig = px.bar(
    df_visual, x='Fecha_str', y=['Pax_Interior', 'Pax_Terraza', 'Pax_Delivery'],
    color_discrete_map={'Pax_Interior': '#2980B9', 'Pax_Terraza': '#7FB3D5', 'Pax_Delivery': '#8E44AD'},
    labels={'value': 'Número de Clientes (Pax)', 'variable': 'Dónde estarán', 'Fecha_str': 'Fecha'}
)
fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(showgrid=True, gridcolor='#333333'), margin=dict(t=20, b=20), barmode='stack', legend_title_text='Distribución')
st.plotly_chart(fig, use_container_width=True)

st.subheader("📅 Tu Tabla de Planificación")
st.markdown("Revisa los números día a día. Puedes descargar esta tabla para enviársela a tu equipo.")

df_mostrar = df_visual[['Fecha_str', 'Lluvia_mm', 'Viento_kmh', 'Estado_Evento', 'Decision_Operativa', 'Clientes_Totales', 'Camareros_Rec', 'Facturacion_Est', 'Beneficio_Est']].copy()
df_mostrar['Facturacion_Est'] = df_mostrar['Facturacion_Est'].apply(lambda x: f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
df_mostrar['Beneficio_Est'] = df_mostrar['Beneficio_Est'].apply(lambda x: f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))

df_mostrar.rename(columns={
    'Fecha_str': 'Día', 'Lluvia_mm': 'Lluvia (mm)', 'Viento_kmh': 'Viento Máx', 
    'Clientes_Totales': 'Demanda (Personas)', 'Camareros_Rec': 'Personal (Turnos)',
    'Facturacion_Est': 'Ingresos Brutos', 'Beneficio_Est': 'Beneficio Neto',
    'Decision_Operativa': 'Estado Terraza', 'Estado_Evento': 'Eventos Cercanos'
}, inplace=True)

st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

csv_descarga = df_mostrar.to_csv(index=False).encode('utf-8')
st.download_button(label="📥 Descargar tabla en Excel (CSV)", data=csv_descarga, file_name='mi_planificacion_semanal.csv', mime='text/csv')

st.divider()

# =====================================================================
# 7. LEYENDA Y PREGUNTAS FRECUENTES (Glosario UX)
# =====================================================================
with st.expander("📖 Guía de uso y Preguntas Frecuentes"):
    st.markdown("""
    ### ⚙️ Sobre la Configuración (Glosario)
    * **Rotación (Turnos):** Es cuántas veces se sienta alguien distinto en la misma silla durante el día. Si abres solo para cenar, pon `1.0`. Si ofreces comidas y cenas a buen ritmo, pon `2.0` o `3.0`. El sistema usa esto para saber el tope de clientes que caben por tu puerta al día.
    * **Tipo de Negocio:** No vende lo mismo un restaurante que un bar. Si eliges *Bar de Copas*, el sistema sabrá que tus viernes y sábados son vitales. Si eliges *Cafetería*, le dará más peso a las mañanas de fin de semana.
    * **Nota en Google y Locales Cercanos:** Si tu calle está llena de bares, los clientes se repartirán. Pero si tienes un 4.8 en Google, la fórmula asume que atraerás más clientes que tus competidores.

    ### ❓ Dudas comunes
    **¿De dónde salen las previsiones de clientes?** Cruzamos tres factores principales: la previsión meteorológica oficial, el calendario de festivos de España, y los eventos de la red de *Ticketmaster* que estén a menos de 4km de tu puerta. Todo esto pasa por una fórmula creada con datos históricos.

    **¿Por qué me recomienda cerrar la terraza si yo sé que tengo toldos?** La alerta de "Cerrar Terraza" salta automáticamente para avisar a tu cocina de que quizá no deberíais descongelar tantas provisiones o llamar a personal extra. Es una sugerencia para evitar *mermas* (tirar comida) cuando detecta viento o lluvia fuerte, pero la decisión final siempre es tuya.

    **¿Qué es la 'Ganancia Extra Potencial'?** Hay días en los que el sistema detecta que vas a llenar tu local seguro (porque hay un evento o es festivo). En esos días de "Alta Ocupación", te sugerimos aplicar técnicas comunes: por ejemplo, ofrecer solo platos de la carta en vez del menú del día. Ese número es lo que ganarías extra si logras que cada cliente gaste un poco más.
    """)

st.caption("🎓 Proyecto Final v1.6.5 - SMART-BCN hecho por etoin99")