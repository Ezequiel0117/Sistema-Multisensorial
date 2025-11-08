from flask import Flask, jsonify, render_template, request
import serial
import time
import random
from datetime import datetime
from collections import deque

app = Flask(__name__)

# Cola para almacenar histórico de lecturas (últimos 50 puntos)
historico_temperatura = deque(maxlen=50)
historico_humo = deque(maxlen=50)
historico_alertas = deque(maxlen=20)

# Umbrales según tu documento (NFPA 72)
UMBRAL_TEMPERATURA_PELIGRO = 60  # °C
UMBRAL_HUMO_PELIGRO = 400  # ppm

# Umbrales para niveles intermedios
UMBRAL_TEMP_BAJO = 25
UMBRAL_TEMP_NORMAL = 40
UMBRAL_TEMP_ALTO = 50

UMBRAL_HUMO_BAJO = 100
UMBRAL_HUMO_NORMAL = 200
UMBRAL_HUMO_ALTO = 300

# Intentar conectar con el Arduino
try:
    arduino = serial.Serial('COM3', 9600, timeout=1)
    time.sleep(2)
    print("Arduino conectado en COM3")
except Exception as e:
    print(f"No se pudo abrir el puerto serie (COM3): {e}. Usando DummyArduino para desarrollo.")
    
    class DummyArduino:
        def __init__(self):
            self.in_waiting = 1
            self.counter = 0
            self.base_temp = 25
            self.base_humo = 50
        
        def readline(self):
            # Simula lecturas realistas del Arduino
            self.counter += 1
            # Variación aleatoria para simular cambios
            temp = self.base_temp + random.uniform(-3, 8)
            humo = self.base_humo + random.uniform(-20, 40)
            humedad = 60 + random.uniform(-10, 10)
            
            # Ocasionalmente simular picos (1% de probabilidad)
            if random.random() < 0.01:
                temp += random.uniform(20, 40)
                humo += random.uniform(200, 300)
            
            # Formato compatible con ambas versiones del Arduino
            # Puedes cambiar entre estos dos formatos según prefieras:
            
            # Formato simplificado (recomendado para Flask):
            data = f"T:{temp:.1f},H:{humo:.1f},RH:{humedad:.1f}"
            
            # Formato del monitor serial (tu código actual):
            # data = f"Temp: {temp:.1f} °C | Humo: {humo:.0f} | Humedad: {humedad:.1f} %"
            
            return data.encode('utf-8')
        
        def write(self, data):
            print(f"DummyArduino.write: {data}")
    
    arduino = DummyArduino()

def calcular_nivel(valor, tipo):
    """Calcula el nivel de alerta según el valor"""
    if tipo == 'temperatura':
        if valor < UMBRAL_TEMP_BAJO:
            return 'bajo'
        elif valor < UMBRAL_TEMP_NORMAL:
            return 'normal'
        elif valor < UMBRAL_TEMP_ALTO:
            return 'alto'
        else:
            return 'peligro'
    else:  # humo
        if valor < UMBRAL_HUMO_BAJO:
            return 'bajo'
        elif valor < UMBRAL_HUMO_NORMAL:
            return 'normal'
        elif valor < UMBRAL_HUMO_ALTO:
            return 'alto'
        else:
            return 'peligro'

def parsear_datos(data_str):
    """
    Parsea los datos del Arduino en múltiples formatos:
    - Formato 1: 'T:25.5,H:123.4' (simplificado)
    - Formato 2: 'Temp: 25.5 °C | Humo: 123 | Humedad: 45.2 %' (tu formato actual)
    """
    try:
        # Intentar formato simplificado primero (T:25.5,H:123.4)
        if 'T:' in data_str and 'H:' in data_str and ',' in data_str:
            partes = data_str.split(',')
            temp = float(partes[0].split(':')[1])
            humo = float(partes[1].split(':')[1])
            return temp, humo
        
        # Intentar formato del monitor serial (Temp: 25.5 °C | Humo: 123 | Humedad: 45.2 %)
        elif 'Temp:' in data_str and 'Humo:' in data_str:
            # Extraer temperatura
            temp_start = data_str.find('Temp:') + 5
            temp_end = data_str.find('°C')
            temp = float(data_str[temp_start:temp_end].strip())
            
            # Extraer humo (valor analógico 0-1023)
            humo_start = data_str.find('Humo:') + 5
            humo_end = data_str.find('|', humo_start)
            humo = float(data_str[humo_start:humo_end].strip())
            
            return temp, humo
        else:
            return None, None
    except Exception as e:
        print(f"Error al parsear datos: {e}, Data: {data_str}")
        return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/leer', methods=['GET'])
def leer():
    if arduino.in_waiting > 0:
        data = arduino.readline().decode('utf-8').strip()
        temp, humo = parsear_datos(data)
        
        if temp is not None and humo is not None:
            # Agregar al histórico
            timestamp = datetime.now().strftime('%H:%M:%S')
            historico_temperatura.append({'time': timestamp, 'value': temp})
            historico_humo.append({'time': timestamp, 'value': humo})
            
            # Calcular niveles
            nivel_temp = calcular_nivel(temp, 'temperatura')
            nivel_humo = calcular_nivel(humo, 'humo')
            
            # Determinar si hay alerta
            alerta_activa = (nivel_temp == 'peligro' or nivel_humo == 'peligro')
            
            # Registrar alerta si es necesaria
            if alerta_activa:
                alerta = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'temperatura': temp,
                    'humo': humo,
                    'tipo': []
                }
                if nivel_temp == 'peligro':
                    alerta['tipo'].append('temperatura')
                if nivel_humo == 'peligro':
                    alerta['tipo'].append('humo')
                
                # Evitar duplicados consecutivos
                if not historico_alertas or historico_alertas[-1]['timestamp'] != alerta['timestamp']:
                    historico_alertas.append(alerta)
            
            return jsonify({
                'temperatura': temp,
                'humo': humo,
                'nivel_temperatura': nivel_temp,
                'nivel_humo': nivel_humo,
                'alerta': alerta_activa,
                'timestamp': timestamp
            })
    
    return jsonify({
        'temperatura': 0,
        'humo': 0,
        'nivel_temperatura': 'sin_datos',
        'nivel_humo': 'sin_datos',
        'alerta': False,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/historico', methods=['GET'])
def historico():
    return jsonify({
        'temperatura': list(historico_temperatura),
        'humo': list(historico_humo)
    })

@app.route('/alertas', methods=['GET'])
def alertas():
    return jsonify({
        'alertas': list(historico_alertas)
    })

@app.route('/led/<accion>', methods=['POST'])
def led(accion):
    if accion == 'on':
        arduino.write(b'L')
    elif accion == 'off':
        arduino.write(b'l')
    return jsonify({'estado': accion})

@app.route('/configuracion', methods=['GET', 'POST'])
def configuracion():
    global UMBRAL_TEMPERATURA_PELIGRO, UMBRAL_HUMO_PELIGRO
    
    if request.method == 'POST':
        data = request.get_json()
        UMBRAL_TEMPERATURA_PELIGRO = data.get('umbral_temperatura', UMBRAL_TEMPERATURA_PELIGRO)
        UMBRAL_HUMO_PELIGRO = data.get('umbral_humo', UMBRAL_HUMO_PELIGRO)
        return jsonify({'success': True})
    
    return jsonify({
        'umbral_temperatura': UMBRAL_TEMPERATURA_PELIGRO,
        'umbral_humo': UMBRAL_HUMO_PELIGRO
    })

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)