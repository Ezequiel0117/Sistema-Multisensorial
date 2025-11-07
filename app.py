from flask import Flask, jsonify, render_template, request
import serial
import time

app = Flask(__name__)

# Intentar conectar con el Arduino; si falla, usar un stub para desarrollo
try:
    arduino = serial.Serial('COM3', 9600, timeout=1)
    time.sleep(2)  # Wait for the connection to establish
    print("Arduino conectado en COM3")
except Exception as e:
    print(f"No se pudo abrir el puerto serie (COM3): {e}. Usando DummyArduino para desarrollo.")
    
    class DummyArduino:
        def __init__(self):
            self.in_waiting = 1  # Cambiado a 1 para simular datos
            self.counter = 0
        
        def readline(self):
            # Simula lecturas del Arduino para desarrollo
            self.counter += 1
            return f'Lectura simulada #{self.counter}'.encode('utf-8')
        
        def write(self, data):
            # No hace nada, solo imprime para debugging en desarrollo
            print(f"DummyArduino.write: {data}")
    
    arduino = DummyArduino()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/leer', methods=['GET'])
def leer():
    if arduino.in_waiting > 0:
        data = arduino.readline().decode('utf-8').strip()
        return jsonify({'lectura': data, 'alerta': False})
    return jsonify({'lectura': 'Sin datos', 'alerta': False})

@app.route('/led/<accion>', methods=['POST'])
def led(accion):
    if accion == 'on':
        arduino.write(b'L')  # L mayúscula para encender
    elif accion == 'off':
        arduino.write(b'l')  # l minúscula para apagar
    return jsonify({'estado': accion})

if __name__ == '__main__':
    app.run(debug=True)