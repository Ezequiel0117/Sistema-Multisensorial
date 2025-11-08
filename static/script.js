// Variables globales
let graficoTemperatura = null;
let graficoHumo = null;
let alertaActiva = false;
let alertaCerradaManualmente = false;  // Nueva variable para controlar cierre manual
let ultimoEstadoPeligro = false;       // Para detectar cambios de estado

// Inicializar gráficos al cargar la página
document.addEventListener('DOMContentLoaded', function() {
    inicializarGraficos();
    actualizar();
    actualizarHistorico();
    actualizarAlertas();
    
    // Actualizar cada segundo
    setInterval(actualizar, 1000);
    
    // Actualizar histórico cada 5 segundos
    setInterval(actualizarHistorico, 5000);
    
    // Actualizar alertas cada 3 segundos
    setInterval(actualizarAlertas, 3000);
});

// Inicializar gráficos con Chart.js
function inicializarGraficos() {
    const ctxTemp = document.getElementById('grafico-temperatura').getContext('2d');
    const ctxHumo = document.getElementById('grafico-humo').getContext('2d');
    
    const configBase = {
        type: 'line',
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            },
            animation: {
                duration: 750
            }
        }
    };
    
    graficoTemperatura = new Chart(ctxTemp, {
        ...configBase,
        data: {
            labels: [],
            datasets: [{
                label: 'Temperatura (°C)',
                data: [],
                borderColor: 'rgb(30, 60, 114)',
                backgroundColor: 'rgba(30, 60, 114, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        }
    });
    
    graficoHumo = new Chart(ctxHumo, {
        ...configBase,
        data: {
            labels: [],
            datasets: [{
                label: 'Humo (ppm)',
                data: [],
                borderColor: 'rgb(220, 53, 69)',
                backgroundColor: 'rgba(220, 53, 69, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        }
    });
}

// Actualizar lecturas en tiempo real
function actualizar() {
    fetch('/leer')
        .then(res => res.json())
        .then(data => {
            // Actualizar valores
            document.getElementById('temp-valor').textContent = data.temperatura.toFixed(1);
            document.getElementById('humo-valor').textContent = data.humo.toFixed(1);
            
            // Actualizar estados
            actualizarEstado('temp-estado', data.nivel_temperatura);
            actualizarEstado('humo-estado', data.nivel_humo);
            
            // Actualizar timestamp
            document.getElementById('ultima-actualizacion').textContent = 
                `Última actualización: ${data.timestamp}`;
            
            // Actualizar conexión
            document.getElementById('estado-conexion').textContent = '● Conectado';
            document.getElementById('estado-conexion').className = 'conectado';
            
            // Manejar alerta de emergencia
            if (data.alerta && !alertaActiva) {
                // Nueva alerta detectada
                if (!alertaCerradaManualmente || !ultimoEstadoPeligro) {
                    // Mostrar solo si no fue cerrada manualmente O si es una nueva alerta
                    mostrarAlertaEmergencia(data);
                    alertaActiva = true;
                    ultimoEstadoPeligro = true;
                }
            } else if (!data.alerta && alertaActiva) {
                // Ya no hay peligro, cerrar alerta automáticamente
                ocultarAlertaEmergencia();
                alertaActiva = false;
                alertaCerradaManualmente = false;  // Reset para la próxima alerta
                ultimoEstadoPeligro = false;
            }
        })
        .catch(error => {
            console.error('Error al actualizar:', error);
            document.getElementById('estado-conexion').textContent = '● Desconectado';
            document.getElementById('estado-conexion').className = 'desconectado';
        });
}

// Actualizar el estado visual de los indicadores
function actualizarEstado(elementId, nivel) {
    const elemento = document.getElementById(elementId);
    elemento.className = `estado-indicador ${nivel}`;
    
    const textos = {
        'bajo': 'BAJO',
        'normal': 'NORMAL',
        'alto': 'ALTO',
        'peligro': '¡PELIGRO!',
        'sin_datos': 'SIN DATOS'
    };
    
    elemento.querySelector('.estado-texto').textContent = textos[nivel] || 'DESCONOCIDO';
}

// Mostrar alerta de emergencia
function mostrarAlertaEmergencia(data) {
    const alertaDiv = document.getElementById('alerta-emergencia');
    const mensaje = document.getElementById('alerta-mensaje');
    const tempSpan = document.getElementById('alerta-temp');
    const humoSpan = document.getElementById('alerta-humo');
    
    mensaje.textContent = 'Se han detectado niveles peligrosos. ¡Evacuar inmediatamente!';
    tempSpan.textContent = `🌡️ ${data.temperatura.toFixed(1)}°C`;
    humoSpan.textContent = `💨 ${data.humo.toFixed(1)} ppm`;
    
    alertaDiv.classList.remove('oculto');
    
    // Reproducir sonido de alerta (opcional)
    reproducirSonidoAlerta();
}

// Ocultar alerta de emergencia
function ocultarAlertaEmergencia() {
    document.getElementById('alerta-emergencia').classList.add('oculto');
}

// Cerrar alerta manualmente (nuevo)
function cerrarAlertaManual() {
    alertaCerradaManualmente = true;
    alertaActiva = false;
    ocultarAlertaEmergencia();
    mostrarNotificacion('ℹ️ Alerta cerrada. Se volverá a mostrar si persiste el peligro.', 'info');
}

// Reproducir sonido de alerta (opcional)
function reproducirSonidoAlerta() {
    // Crear un beep usando Web Audio API
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.value = 800;
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.5);
}

// Actualizar gráficos históricos
function actualizarHistorico() {
    fetch('/historico')
        .then(res => res.json())
        .then(data => {
            // Actualizar gráfico de temperatura
            if (data.temperatura.length > 0) {
                const labelsTemp = data.temperatura.map(d => d.time);
                const valuesTemp = data.temperatura.map(d => d.value);
                
                graficoTemperatura.data.labels = labelsTemp;
                graficoTemperatura.data.datasets[0].data = valuesTemp;
                graficoTemperatura.update('none'); // Sin animación para mejor rendimiento
            }
            
            // Actualizar gráfico de humo
            if (data.humo.length > 0) {
                const labelsHumo = data.humo.map(d => d.time);
                const valuesHumo = data.humo.map(d => d.value);
                
                graficoHumo.data.labels = labelsHumo;
                graficoHumo.data.datasets[0].data = valuesHumo;
                graficoHumo.update('none');
            }
        })
        .catch(error => {
            console.error('Error al actualizar histórico:', error);
        });
}

// Actualizar registro de alertas
function actualizarAlertas() {
    fetch('/alertas')
        .then(res => res.json())
        .then(data => {
            const listaAlertas = document.getElementById('lista-alertas');
            
            if (data.alertas.length === 0) {
                listaAlertas.innerHTML = '<p class="sin-alertas">No hay alertas registradas</p>';
            } else {
                listaAlertas.innerHTML = '';
                
                // Mostrar alertas en orden inverso (más reciente primero)
                data.alertas.slice().reverse().forEach(alerta => {
                    const alertaDiv = document.createElement('div');
                    alertaDiv.className = 'alerta-item';
                    
                    const tiposTexto = alerta.tipo.map(t => 
                        t === 'temperatura' ? '🌡️ Temperatura' : '💨 Humo'
                    ).join(' y ');
                    
                    alertaDiv.innerHTML = `
                        <div class="alerta-item-header">
                            <strong>⚠️ Alerta: ${tiposTexto}</strong>
                            <span>${alerta.timestamp}</span>
                        </div>
                        <div class="alerta-item-detalles">
                            <span>Temperatura: ${alerta.temperatura.toFixed(1)}°C</span>
                            <span>Humo: ${alerta.humo.toFixed(1)} ppm</span>
                        </div>
                    `;
                    
                    listaAlertas.appendChild(alertaDiv);
                });
            }
        })
        .catch(error => {
            console.error('Error al actualizar alertas:', error);
        });
}

// Funciones de control LED
function encender() {
    fetch('/led/on', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            console.log('LED encendido:', data);
            mostrarNotificacion('✅ LED encendido correctamente', 'success');
        })
        .catch(error => {
            console.error('Error al encender LED:', error);
            mostrarNotificacion('❌ Error al encender LED', 'error');
        });
}

function apagar() {
    fetch('/led/off', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            console.log('LED apagado:', data);
            mostrarNotificacion('✅ LED apagado correctamente', 'success');
        })
        .catch(error => {
            console.error('Error al apagar LED:', error);
            mostrarNotificacion('❌ Error al apagar LED', 'error');
        });
}

// Mostrar notificaciones temporales
function mostrarNotificacion(mensaje, tipo) {
    const notif = document.createElement('div');
    notif.className = `notificacion ${tipo}`;
    notif.textContent = mensaje;
    
    let bgColor;
    switch(tipo) {
        case 'success':
            bgColor = '#28a745';
            break;
        case 'error':
            bgColor = '#dc3545';
            break;
        case 'info':
            bgColor = '#17a2b8';
            break;
        default:
            bgColor = '#6c757d';
    }
    
    notif.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 2rem;
        background: ${bgColor};
        color: white;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        z-index: 10000;
        animation: slideInRight 0.3s ease;
        max-width: 400px;
        word-wrap: break-word;
    `;
    
    document.body.appendChild(notif);
    
    setTimeout(() => {
        notif.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notif.remove(), 300);
    }, 3000);
}