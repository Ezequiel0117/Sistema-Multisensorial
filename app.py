from flask import Flask, jsonify, render_template, request, session, redirect, url_for
import serial
import time
import random
from datetime import datetime
from collections import deque
import threading
import sqlite3
import hashlib
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ============================================
# CONFIGURACIÓN DE EMAIL (GMAIL GRATIS)
# ============================================
# ⚠️ RECUERDA REEMPLAZAR CON TUS CREDENCIALES
EMAIL_ENABLED = True
GMAIL_USER = "tucorreo@gmail.com"
GMAIL_APP_PASSWORD = "tucontraseña"

def enviar_email(destinatario, asunto, cuerpo):
    """Envía email usando Gmail SMTP"""
    if not EMAIL_ENABLED:
        print(f"[SIMULADO] Email a {destinatario}: {asunto}")
        return True

    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = destinatario
        msg['Subject'] = asunto
        msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        text = msg.as_string()
        server.sendmail(GMAIL_USER, destinatario, text)
        server.quit()
        print(f"Email enviado a {destinatario}")
        return True
    except Exception as e:
        print(f"Error al enviar email a {destinatario}: {e}")
        return False

# Cola para histórico
historico_temperatura = deque(maxlen=50)
historico_humo = deque(maxlen=50)
historico_alertas = deque(maxlen=20)

# Estado maestro de peligro (para "enganchar" la alerta)
estado_peligro_anterior = False

# Última lectura
ultima_lectura = {
    'temperatura': 0, 'humo': 0,
    'nivel_temperatura': 'bajo', 'nivel_humo': 'bajo',
    'alerta': False, 'timestamp': datetime.now().strftime('%H:%M:%S')
}

lectura_lock = threading.Lock()

# 🔑 UMBRALES (Basados en tu app.py y leyenda originales)
UMBRAL_TEMPERATURA_PELIGRO = 45 
UMBRAL_HUMO_PELIGRO = 600 
UMBRAL_TEMP_BAJO, UMBRAL_TEMP_NORMAL, UMBRAL_TEMP_ALTO = 20, 30, 40
UMBRAL_HUMO_BAJO, UMBRAL_HUMO_NORMAL, UMBRAL_HUMO_ALTO = 100, 300, 500


# Arduino (real o dummy)
try:
    arduino = serial.Serial('COM7', 9600, timeout=0.1)
    time.sleep(2)
    print("Arduino conectado en COM7")
    usar_dummy = False
except Exception as e:
    print(f"No se pudo conectar al Arduino: {e}. Usando DummyArduino.")
    
    class DummyArduino:
        def __init__(self):
            self.counter = 0
            # Valores base normales
            self.base_temp = 25
            self.base_humo = 50
        def readline(self):
            self.counter += 1
            temp = self.base_temp + random.uniform(-3, 8)
            humo = self.base_humo + random.uniform(-20, 40)
            
            # 1% de probabilidad de generar un pico de peligro
            if random.random() < 0.01: 
                print("***********************************")
                print("Dummy: Simulando pico de peligro...")
                print("***********************************")
                temp += random.uniform(30, 40) # Supera 45
                humo += random.uniform(550, 650) # Supera 600
                
            return f"T:{temp:.1f},H:{humo:.1f},RH:60.0".encode('utf-8')
        def write(self, data): 
            print(f"Dummy.write: {data}")
            return len(data)
    
    arduino = DummyArduino()
    usar_dummy = True

# ============================================
# BASE DE DATOS (Incluye la columna 'rol' para Admin)
# ============================================
def inicializar_db():
    conn = sqlite3.connect('alertas.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios
              (id INTEGER PRIMARY KEY AUTOINCREMENT,
               nombre TEXT NOT NULL,
               email TEXT UNIQUE NOT NULL,
               telefono TEXT,
               password_hash TEXT NOT NULL,
               rol TEXT DEFAULT 'usuario', 
               notificaciones_activas INTEGER DEFAULT 1,
               fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS notificaciones
              (id INTEGER PRIMARY KEY AUTOINCREMENT,
               usuario_id INTEGER,
               tipo TEXT NOT NULL,
               temperatura REAL,
               humo REAL,
               mensaje TEXT,
               enviado INTEGER DEFAULT 0,
               fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY (usuario_id) REFERENCES usuarios(id))''')
    
    conn.commit()
    
    # Crear usuario admin por defecto si no existe
    c.execute("SELECT * FROM usuarios WHERE email = 'admin@sistema.com'")
    if not c.fetchone():
        c.execute('''INSERT INTO usuarios (nombre, email, telefono, password_hash, rol)
                    VALUES (?, ?, ?, ?, ?)''',
                  ('Administrador', 'admin@sistema.com', '', 
                   hash_password('admin123'), 'admin'))
        conn.commit()
        print("✅ Usuario admin creado: admin@sistema.com / admin123")
    
    conn.close()
    print("✅ Base de datos inicializada")

def hash_password(p): 
    return hashlib.sha256(p.encode()).hexdigest()

def registrar_usuario(nombre, email, telefono, password):
    try:
        conn = sqlite3.connect('alertas.db')
        c = conn.cursor()
        c.execute('INSERT INTO usuarios (nombre, email, telefono, password_hash) VALUES (?, ?, ?, ?)',
                  (nombre, email, telefono, hash_password(password)))
        conn.commit()
        uid = c.lastrowid
        conn.close()
        return True, uid
    except sqlite3.IntegrityError:
        return False, "Email ya registrado"
    except Exception as e:
        return False, str(e)

def verificar_usuario(email, password):
    """Verifica las credenciales del usuario (incluyendo ROL)"""
    try:
        conn = sqlite3.connect('alertas.db')
        c = conn.cursor()
        
        password_hash = hash_password(password)
        c.execute('''SELECT id, nombre, telefono, notificaciones_activas, rol 
                     FROM usuarios WHERE email = ? AND password_hash = ?''',
                  (email, password_hash))
        
        u = c.fetchone()
        conn.close()
        
        if u:
            return True, {
                'id': u[0], 
                'nombre': u[1], 
                'telefono': u[2], 
                'notificaciones_activas': u[3],
                'rol': u[4]
            }
        return False, "Credenciales incorrectas"
    except Exception as e:
        return False, str(e)

def obtener_usuarios_notificables():
    try:
        conn = sqlite3.connect('alertas.db')
        c = conn.cursor()
        c.execute('SELECT id, nombre, email FROM usuarios WHERE notificaciones_activas = 1')
        usuarios = c.fetchall()
        conn.close()
        return [{'id': u[0], 'nombre': u[1], 'email': u[2]} for u in usuarios]
    except Exception as e:
        print(f"Error usuarios: {e}")
        return []

def registrar_notificacion_db(uid, tipo, temp, humo, msg, enviado):
    try:
        conn = sqlite3.connect('alertas.db')
        c = conn.cursor()
        c.execute('INSERT INTO notificaciones (usuario_id, tipo, temperatura, humo, mensaje, enviado) VALUES (?, ?, ?, ?, ?, ?)',
                  (uid, tipo, temp, humo, msg, enviado))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error DB notif: {e}")

# ============================================
# NOTIFICACIÓN POR EMAIL (SIN SPAM)
# ============================================
def notificar_usuarios_alerta(temp, humo, tipo_alerta):
    """Notifica a usuarios solo cuando es necesario (llamado solo desde cambio de estado a peligro)"""

    usuarios = obtener_usuarios_notificables()
    if not usuarios:
        print("No hay usuarios para notificar")
        return

    if 'emergencia_manual' in tipo_alerta:
        asunto = "🚨 EMERGENCIA ACTIVADA MANUALMENTE"
        cuerpo = f"""\
🚨 ¡EMERGENCIA ACTIVADA POR ADMINISTRADOR!
El administrador ha activado manualmente el protocolo de emergencia.
¡EVACUAR INMEDIATAMENTE!
Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    elif 'temperatura' in tipo_alerta and 'humo' in tipo_alerta:
        asunto = "ALERTA CRÍTICA: Incendio Detectado"
        cuerpo = f"""\
🚨 ¡ALERTA CRÍTICA!
Se ha detectado una emergencia por MÚLTIPLES RIESGOS:
- Temperatura: {temp:.1f}°C (Umbral: {UMBRAL_TEMPERATURA_PELIGRO}°C)
- Humo: {humo:.0f} ppm (Umbral: {UMBRAL_HUMO_PELIGRO} ppm)
¡EVACUAR INMEDIATAMENTE!
Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    elif 'temperatura' in tipo_alerta:
        asunto = "ALERTA: Temperatura Alta"
        cuerpo = f"""\
🔥 ¡PELIGRO DE INCENDIO!
Temperatura crítica detectada:
- Temperatura: {temp:.1f}°C (Umbral: {UMBRAL_TEMPERATURA_PELIGRO}°C)
Verificar inmediatamente.
Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    else: # Solo Humo
        asunto = "ALERTA: Humo Detectado"
        cuerpo = f"""\
💨 ¡HUMO DETECTADO!
Nivel de humo elevado:
- Humo: {humo:.0f} ppm (Umbral: {UMBRAL_HUMO_PELIGRO} ppm)
Evacuar el área.
Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""

    for u in usuarios:
        enviado = enviar_email(u['email'], asunto, cuerpo)
        registrar_notificacion_db(u['id'], ','.join(tipo_alerta), temp, humo, cuerpo, 1 if enviado else 0)

    print(f"✅ Notificación enviada a {len(usuarios)} usuario(s): {', '.join(tipo_alerta)}")

# Inicializar DB
inicializar_db()

# --------------------------------------------
# FUNCIÓN CORREGIDA: Usa UMBRAL_..._PELIGRO
# --------------------------------------------
def calcular_nivel(valor, tipo):
    """Clasifica el valor en bajo, normal, alto o peligro."""
    if tipo == 'temperatura':
        if valor >= UMBRAL_TEMPERATURA_PELIGRO: return 'peligro' # 45
        elif valor >= UMBRAL_TEMP_ALTO: return 'alto' # 40
        elif valor >= UMBRAL_TEMP_NORMAL: return 'normal' # 30
        elif valor >= UMBRAL_TEMP_BAJO: return 'bajo' # 20
        else: return 'bajo'
    else:
        if valor >= UMBRAL_HUMO_PELIGRO: return 'peligro' # 600
        elif valor >= UMBRAL_HUMO_ALTO: return 'alto' # 500
        elif valor >= UMBRAL_HUMO_NORMAL: return 'normal' # 300
        elif valor >= UMBRAL_HUMO_BAJO: return 'bajo' # 100
        else: return 'bajo'
# --------------------------------------------

def parsear_datos(data_str):
    try:
        if 'T:' in data_str and 'H:' in data_str:
            partes = data_str.split(',')
            temp = float(partes[0].split(':')[1])
            humo = float(partes[1].split(':')[1])
            return temp, humo
        elif 'Temp:' in data_str and 'Humo:' in data_str:
            temp = float(data_str.split('Temp:')[1].split('°')[0].strip())
            humo = float(data_str.split('Humo:')[1].split('|')[0].strip())
            return temp, humo
    except: pass
    return None, None

# --------------------------------------------
# 🔑 FUNCIÓN DE LECTURA CORREGIDA (CON "LATCH")
# --------------------------------------------
def leer_arduino_continuo():
    global ultima_lectura, estado_peligro_anterior
    print("📡 Lectura continua iniciada...")
    
    while True:
        try:
            if usar_dummy:
                data = arduino.readline().decode('utf-8', errors='ignore').strip()
            else:
                arduino.reset_input_buffer()
                data = arduino.readline().decode('utf-8', errors='ignore').strip()

            if data:
                temp, humo = parsear_datos(data)
                if temp is not None and humo is not None:
                    with lectura_lock:
                        ts = datetime.now().strftime('%H:%M:%S')
                        historico_temperatura.append({'time': ts, 'value': temp})
                        historico_humo.append({'time': ts, 'value': humo})
                        
                        # 1. Calcular niveles actuales
                        nivel_temp = calcular_nivel(temp, 'temperatura')
                        nivel_humo = calcular_nivel(humo, 'humo')
                        
                        # 2. Determinar si esta lectura específica es peligrosa
                        peligro_en_esta_lectura = nivel_temp == 'peligro' or nivel_humo == 'peligro'

                        # 3. LÓGICA DE TRANSICIÓN: Detectar un NUEVO peligro
                        if peligro_en_esta_lectura and not estado_peligro_anterior:
                            # CAMBIO DE ESTADO: Seguro -> Peligro
                            print("🚨 ¡NUEVA ALERTA DETECTADA! Enganchando estado de peligro.")
                            tipos = []
                            if nivel_temp == 'peligro': tipos.append('temperatura')
                            if nivel_humo == 'peligro': tipos.append('humo')
                            
                            alerta_data = {
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'temperatura': temp, 
                                'humo': humo, 
                                'tipo': tipos
                            }
                            historico_alertas.append(alerta_data)
                            
                            # 🔑 ENVÍA EL EMAIL (SOLO 1 VEZ)
                            threading.Thread(
                                target=notificar_usuarios_alerta,
                                args=(temp, humo, tipos),
                                daemon=True
                            ).start()
                            
                            # ENGANCHAR EL ESTADO
                            estado_peligro_anterior = True

                        # 4. LÓGICA DE TRANSICIÓN: Detectar que el peligro HA PASADO
                        elif not peligro_en_esta_lectura and estado_peligro_anterior:
                            # CAMBIO DE ESTADO: Peligro -> Seguro
                            print("✅ El peligro ha pasado. Reseteando estado.")
                            
                            # SOLTAR EL ESTADO
                            estado_peligro_anterior = False

                        # 5. Actualizar la última lectura para el cliente
                        # La bandera 'alerta' AHORA refleja el estado "enganchado"
                        ultima_lectura.update({
                            'temperatura': temp, 
                            'humo': humo,
                            'nivel_temperatura': nivel_temp, 
                            'nivel_humo': nivel_humo,
                            'alerta': estado_peligro_anterior, # 🔑 El cliente ve el estado "enganchado"
                            'timestamp': ts
                        })

            time.sleep(0.1) 
        except Exception as e:
            print(f"❌ Error lectura: {e}")
            time.sleep(1)

threading.Thread(target=leer_arduino_continuo, daemon=True).start()

# ============================================
# RUTAS FLASK (CON LÓGICA DE ADMIN)
# ============================================
@app.route('/')
def index():
    if 'usuario_id' in session:
        # Esta lógica es necesaria para que funcione el {% if es_admin %} en index.html
        es_admin = False
        if session.get('usuario_rol') == 'admin':
             es_admin = True
             
        return render_template('index.html', 
                               usuario=session.get('usuario_nombre'),
                               es_admin=es_admin) # Pasar es_admin al template
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        exito, res = verificar_usuario(data.get('email'), data.get('password'))
        if exito:
            # Guardar el ROL en la sesión es crucial para el Admin
            session.update({
                'usuario_id': res['id'],
                'usuario_nombre': res['nombre'],
                'usuario_telefono': res['telefono'],
                'usuario_rol': res.get('rol', 'usuario') # Guardar el rol
            })
            return jsonify({'success': True})
        return jsonify({'success': False, 'mensaje': res}), 401
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        data = request.get_json()
        for campo in ['nombre', 'email', 'password']:
            if not data.get(campo):
                return jsonify({'success': False, 'mensaje': f'{campo} requerido'}), 400
        if len(data['password']) < 6:
            return jsonify({'success': False, 'mensaje': 'Contraseña mínima 6 caracteres'}), 400
        exito, res = registrar_usuario(data['nombre'], data['email'], data.get('telefono', ''), data['password'])
        if exito:
            return jsonify({'success': True})
        return jsonify({'success': False, 'mensaje': res}), 400
    return render_template('registro.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/perfil')
def perfil():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('alertas.db')
    c = conn.cursor()
    c.execute('SELECT nombre, email, telefono, notificaciones_activas, fecha_registro FROM usuarios WHERE id = ?', (session['usuario_id'],))
    usuario = c.fetchone()
    c.execute('SELECT tipo, temperatura, humo, mensaje, enviado, fecha FROM notificaciones WHERE usuario_id = ? ORDER BY fecha DESC LIMIT 20', (session['usuario_id'],))
    notifs = c.fetchall()
    conn.close()
    return render_template('perfil.html', usuario=usuario, notificaciones=notifs)

@app.route('/toggle_notificaciones', methods=['POST'])
def toggle_notificaciones():
    if 'usuario_id' not in session:
        return jsonify({'success': False}), 401
    conn = sqlite3.connect('alertas.db')
    c = conn.cursor()
    c.execute('UPDATE usuarios SET notificaciones_activas = NOT notificaciones_activas WHERE id = ?', (session['usuario_id'],))
    c.execute('SELECT notificaciones_activas FROM usuarios WHERE id = ?', (session['usuario_id'],))
    estado = bool(c.fetchone()[0])
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'notificaciones_activas': estado})

@app.route('/leer') 
def leer(): 
    with lectura_lock: 
        return jsonify(ultima_lectura)

@app.route('/historico') 
def historico(): 
    with lectura_lock: 
        return jsonify({'temperatura': list(historico_temperatura), 'humo': list(historico_humo)})

@app.route('/alertas') 
def alertas(): 
    with lectura_lock: 
        return jsonify({'alertas': list(historico_alertas)})

@app.route('/led/<accion>', methods=['POST'])
def led(accion):
    try:
        arduino.write(b'L' if accion == 'on' else b'l')
        return jsonify({'success': True, 'estado': accion})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/ventilador/<accion>', methods=['POST'])
def ventilador(accion):
    # Solo Admin puede usar esto
    if session.get('usuario_rol') != 'admin':
        return jsonify({'success': False, 'mensaje': 'No autorizado'}), 403
    try:
        if accion == 'on':
            arduino.write(b'V')
            print("✅ Ventilador encendido")
        elif accion == 'off':
            arduino.write(b'v')
            print("✅ Ventilador apagado")
        return jsonify({'success': True, 'estado': accion})
    except Exception as e:
        print(f"❌ Error al controlar ventilador: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/servomotor/<accion>', methods=['POST'])
def servomotor(accion):
    # Solo Admin puede usar esto
    if session.get('usuario_rol') != 'admin':
        return jsonify({'success': False, 'mensaje': 'No autorizado'}), 403
    try:
        if accion == 'abrir':
            arduino.write(b'A')
            print("✅ Servomotores: Puertas ABIERTAS")
        elif accion == 'cerrar':
            arduino.write(b'C')
            print("✅ Servomotores: Puertas CERRADAS")
        return jsonify({'success': True, 'estado': accion})
    except Exception as e:
        print(f"❌ Error al controlar servomotor: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/emergencia/manual', methods=['POST'])
def emergencia_manual():
    """Activa emergencia manualmente (solo admin)"""
    global estado_peligro_anterior
    
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'mensaje': 'No autorizado'}), 401
    
    if session.get('usuario_rol') != 'admin':
        return jsonify({'success': False, 'mensaje': 'Solo administradores'}), 403
    
    try:
        # Comandos de hardware
        arduino.write(b'V')
        arduino.write(b'A')
        print("✅ Emergencia manual: Ventilador y puertas activados")
        
        # Registrar en base de datos como alerta manual
        with lectura_lock:
            temp_actual = ultima_lectura['temperatura']
            humo_actual = ultima_lectura['humo']

            alerta = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'temperatura': temp_actual,
                'humo': humo_actual,
                'tipo': ['emergencia_manual']
            }
            historico_alertas.append(alerta)
            
            # ENGANCHAR EL ESTADO
            estado_peligro_anterior = True
            
            # Notificar a usuarios
            threading.Thread(
                target=notificar_usuarios_alerta,
                args=(
                    temp_actual, 
                    humo_actual, 
                    ['emergencia_manual']
                ),
                daemon=True
            ).start()
        
        return jsonify({'success': True, 'mensaje': 'Emergencia activada'})
    except Exception as e:
        print(f"❌ Error en emergencia manual: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/configuracion', methods=['GET', 'POST'])
def configuracion():
    # 🔑 LÍNEA CORREGIDA (eliminando <\ctrl61>O)
    global UMBRAL_TEMPERATURA_PELIGRO, UMBRAL_HUMO_PELIGRO
    
    if request.method == 'POST':
        data = request.get_json()
        UMBRAL_TEMPERATURA_PELIGRO = data.get('umbral_temperatura', UMBRAL_TEMPERATURA_PELIGRO)
        UMBRAL_HUMO_PELIGRO = data.get('umbral_humo', UMBRAL_HUMO_PELIGRO)
        return jsonify({'success': True})
    return jsonify({'umbral_temperatura': UMBRAL_TEMPERATURA_PELIGRO, 'umbral_humo': UMBRAL_HUMO_PELIGRO})

@app.route('/estadisticas')
def estadisticas():
    with lectura_lock:
        if historico_temperatura:
            temps = [x['value'] for x in historico_temperatura]
            humos = [x['value'] for x in historico_humo]
            return jsonify({
                'temp_promedio': sum(temps)/len(temps), 'temp_max': max(temps), 'temp_min': min(temps),
                'humo_promedio': sum(humos)/len(humos), 'humo_max': max(humos), 'humo_min': min(humos),
                'total_alertas': len(historico_alertas), 'lecturas_realizadas': len(historico_temperatura)
            })
        return jsonify({k: 0 for k in ['temp_promedio', 'temp_max', 'temp_min', 'humo_promedio', 'humo_max', 'humo_min', 'total_alertas', 'lecturas_realizadas']})


if __name__ == '__main__':
    print("🚀 Servidor Flask iniciado - Sistema de Alertas Inteligente")
    print("📧 Notificaciones por EMAIL (Gmail)")
    print("✅ Alertas solo se registran al detectar NUEVO peligro (Lógica de Latch Activada)")
    app.run(debug=True, use_reloader=False)