// Variables globales
let graficoTemperatura = null;
let graficoHumo = null;
let alertaActiva = false;
let alertaCerradaManualmente = false;
let tiempoUltimoCierre = 0;
const TIEMPO_REABRIR = 30000; // 30 segundos

// Variables para control de registro de alertas
let ultimoEstadoPeligro = {
    temperatura: false,
    humo: false
};
let tiempoUltimaAlertaRegistrada = 0;
const TIEMPO_MINIMO_ENTRE_ALERTAS = 10000; // 10 segundos entre alertas

// Inicializar gráficos al cargar la página
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Página cargada - Inicializando sistema');
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
                borderColor: 'rgb(30, 64, 175)',
                backgroundColor: 'rgba(30, 64, 175, 0.1)',
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
                borderColor: 'rgb(239, 68, 68)',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
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
            
            // LÓGICA MEJORADA DE DETECCIÓN Y REGISTRO DE ALERTAS
            const hayPeligroTemp = data.nivel_temperatura === 'peligro';
            const hayPeligroHumo = data.nivel_humo === 'peligro';
            const hayPeligro = hayPeligroTemp || hayPeligroHumo;
            
            const tiempoActual = Date.now();
            const tiempoTranscurrido = tiempoActual - tiempoUltimoCierre;
            const tiempoDesdeUltimaAlerta = tiempoActual - tiempoUltimaAlertaRegistrada;
            
            console.log('🔍 Estado:', {
                temp: data.temperatura,
                humo: data.humo,
                nivel_temp: data.nivel_temperatura,
                nivel_humo: data.nivel_humo,
                hayPeligro: hayPeligro,
                alertaActiva: alertaActiva,
                cerradaManualmente: alertaCerradaManualmente,
                tiempoTranscurrido: Math.floor(tiempoTranscurrido / 1000) + 's'
            });
            
            // DETECTAR CAMBIO DE ESTADO A PELIGRO (para registrar alerta)
            const cambioPeligroTemp = hayPeligroTemp && !ultimoEstadoPeligro.temperatura;
            const cambioPeligroHumo = hayPeligroHumo && !ultimoEstadoPeligro.humo;
            const cambioPeligro = cambioPeligroTemp || cambioPeligroHumo;
            
            // REGISTRAR ALERTA SOLO CUANDO:
            // 1. Hay un cambio de estado a peligro Y
            // 2. Ha pasado el tiempo mínimo desde la última alerta
            if (cambioPeligro && tiempoDesdeUltimaAlerta > TIEMPO_MINIMO_ENTRE_ALERTAS) {
                console.log('📝 REGISTRANDO NUEVA ALERTA - Cambio de estado detectado');
                registrarAlertaEnServidor(data, hayPeligroTemp, hayPeligroHumo);
                tiempoUltimaAlertaRegistrada = tiempoActual;
            }
            
            // LÓGICA SIMPLIFICADA PARA MOSTRAR MODAL DE ALERTA
            if (hayPeligro) {
                console.log('⚠️ HAY PELIGRO DETECTADO - Verificando si mostrar modal');
                
                // Verificar si la alerta fue cerrada manualmente recientemente
                const fueCerradaRecientemente = alertaCerradaManualmente && tiempoTranscurrido < TIEMPO_REABRIR;
                
                if (!alertaActiva && !fueCerradaRecientemente) {
                    console.log('🚨 MOSTRANDO MODAL DE ALERTA');
                    mostrarAlertaEmergencia(data);
                    alertaActiva = true;
                } else if (fueCerradaRecientemente) {
                    console.log('⏳ Alerta suprimida - Esperando ' + Math.ceil((TIEMPO_REABRIR - tiempoTranscurrido) / 1000) + 's más');
                }
            } else {
                // No hay peligro - cerrar alerta visual si está activa
                if (alertaActiva) {
                    console.log('✅ Sin peligro - Cerrando alerta automáticamente');
                    ocultarAlertaEmergencia();
                    alertaActiva = false;
                    // Reset cuando no hay peligro
                    alertaCerradaManualmente = false;
                }
            }
            
            // Actualizar estado anterior para la próxima comparación
            ultimoEstadoPeligro.temperatura = hayPeligroTemp;
            ultimoEstadoPeligro.humo = hayPeligroHumo;
        })
        .catch(error => {
            console.error('❌ Error al actualizar:', error);
            document.getElementById('estado-conexion').textContent = '● Desconectado';
            document.getElementById('estado-conexion').className = 'desconectado';
        });
}

// Función para registrar alerta en el servidor
function registrarAlertaEnServidor(data, peligroTemp, peligroHumo) {
    const tiposAlerta = [];
    if (peligroTemp) tiposAlerta.push('temperatura');
    if (peligroHumo) tiposAlerta.push('humo');
    
    fetch('/alertas/registrar', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            temperatura: data.temperatura,
            humo: data.humo,
            tipo: tiposAlerta,
            timestamp: new Date().toLocaleString()
        })
    })
    .then(res => res.json())
    .then(resultado => {
        console.log('✅ Alerta registrada en servidor:', resultado);
        // Actualizar la lista de alertas inmediatamente
        actualizarAlertas();
    })
    .catch(error => {
        console.error('❌ Error al registrar alerta:', error);
    });
}

// Actualizar el estado visual de los indicadores
function actualizarEstado(elementId, nivel) {
    const elemento = document.getElementById(elementId);
    if (!elemento) {
        console.error('No se encontró el elemento:', elementId);
        return;
    }
    
    elemento.className = `estado-indicador ${nivel}`;
    
    const textos = {
        'bajo': 'BAJO',
        'normal': 'NORMAL',
        'alto': 'ALTO',
        'peligro': '¡PELIGRO!',
        'sin_datos': 'SIN DATOS'
    };
    
    const estadoTexto = elemento.querySelector('.estado-texto');
    if (estadoTexto) {
        estadoTexto.textContent = textos[nivel] || 'DESCONOCIDO';
    }
}

// Mostrar alerta de emergencia
function mostrarAlertaEmergencia(data) {
    console.log('📢 Ejecutando mostrarAlertaEmergencia()');
    
    const alertaDiv = document.getElementById('alerta-emergencia');
    if (!alertaDiv) {
        console.error('❌ No se encontró el elemento alerta-emergencia');
        return;
    }
    
    const mensaje = document.getElementById('alerta-mensaje');
    const tempSpan = document.getElementById('alerta-temp');
    const humoSpan = document.getElementById('alerta-humo');
    
    if (mensaje) mensaje.textContent = 'Se han detectado niveles peligrosos. ¡Evacuar inmediatamente!';
    if (tempSpan) tempSpan.textContent = `🌡️ ${data.temperatura.toFixed(1)}°C`;
    if (humoSpan) humoSpan.textContent = `💨 ${data.humo.toFixed(1)} ppm`;
    
    // Remover clase oculto
    alertaDiv.classList.remove('oculto');
    console.log('✅ Modal mostrado - Clases:', alertaDiv.className);
    
    // Reproducir sonido
    reproducirSonidoAlerta();
}

// Ocultar alerta de emergencia
function ocultarAlertaEmergencia() {
    console.log('🔇 Ocultando alerta de emergencia');
    const alertaDiv = document.getElementById('alerta-emergencia');
    if (alertaDiv) {
        alertaDiv.classList.add('oculto');
        console.log('✅ Modal oculto - Clases:', alertaDiv.className);
    }
}

// Cerrar alerta manualmente
function cerrarAlertaManual(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    console.log('👆 Usuario cerró la alerta manualmente');
    
    alertaCerradaManualmente = true;
    alertaActiva = false;
    tiempoUltimoCierre = Date.now();
    
    ocultarAlertaEmergencia();
    
    const segundosEspera = TIEMPO_REABRIR / 1000;
    mostrarNotificacion(
        `ℹ️ Alerta cerrada. Se volverá a mostrar en ${segundosEspera}s si persiste el peligro.`,
        'info'
    );
}

// Reproducir sonido de alerta
function reproducirSonidoAlerta() {
    try {
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
        
        console.log('🔊 Sonido de alerta reproducido');
    } catch (error) {
        console.log('🔇 No se pudo reproducir el sonido:', error);
    }
}

// Actualizar gráficos históricos
function actualizarHistorico() {
    fetch('/historico')
        .then(res => res.json())
        .then(data => {
            if (data.temperatura.length > 0) {
                const labelsTemp = data.temperatura.map(d => d.time);
                const valuesTemp = data.temperatura.map(d => d.value);
                
                graficoTemperatura.data.labels = labelsTemp;
                graficoTemperatura.data.datasets[0].data = valuesTemp;
                graficoTemperatura.update('none');
            }
            
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
                
                data.alertas.slice().reverse().forEach(alerta => {
                    const alertaDiv = document.createElement('div');
                    alertaDiv.className = 'alerta-item';
                    
                    const tiposTexto = alerta.tipo.map(t => {
                        if (t === 'temperatura') return '🌡️ Temperatura';
                        if (t === 'humo') return '💨 Humo';
                        if (t === 'emergencia_manual') return '🚨 Emergencia Manual';
                        return t;
                    }).join(' y ');
                    
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

// BOTÓN DE EMERGENCIA MANUAL
function activarEmergenciaManual() {
    if (!confirm('¿Está seguro de que desea activar el modo de emergencia? Esto encenderá el ventilador y abrirá las puertas.')) {
        return;
    }
    
    mostrarNotificacion('🚨 Activando modo de emergencia...', 'info');
    
    fetch('/emergencia/manual', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // Registrar alerta manual
                registrarAlertaEnServidor(
                    {temperatura: 0, humo: 0}, 
                    false, 
                    false
                );
                mostrarNotificacion('🚨 MODO DE EMERGENCIA ACTIVADO: Ventilador encendido y puertas abiertas', 'success');
            } else {
                mostrarNotificacion(`❌ Error: ${data.mensaje || 'No se pudo activar la emergencia'}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error al activar emergencia:', error);
            mostrarNotificacion('❌ Error al activar modo de emergencia', 'error');
        });
}

// Funciones de control del Ventilador
function encenderVentilador() {
    fetch('/ventilador/on', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            console.log('Ventilador encendido:', data);
            mostrarNotificacion('🌀 Ventilador encendido - Evacuando humo', 'success');
        })
        .catch(error => {
            console.error('Error al encender ventilador:', error);
            mostrarNotificacion('❌ Error al encender ventilador', 'error');
        });
}

function apagarVentilador() {
    fetch('/ventilador/off', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            console.log('Ventilador apagado:', data);
            mostrarNotificacion('⏹️ Ventilador apagado', 'success');
        })
        .catch(error => {
            console.error('Error al apagar ventilador:', error);
            mostrarNotificacion('❌ Error al apagar ventilador', 'error');
        });
}

// Funciones de control de Servomotores
function abrirPuertas() {
    fetch('/servomotor/abrir', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            console.log('Puertas abiertas:', data);
            mostrarNotificacion('🔓 Puertas de evacuación ABIERTAS', 'success');
        })
        .catch(error => {
            console.error('Error al abrir puertas:', error);
            mostrarNotificacion('❌ Error al abrir puertas', 'error');
        });
}

function cerrarPuertas() {
    fetch('/servomotor/cerrar', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            console.log('Puertas cerradas:', data);
            mostrarNotificacion('🔒 Puertas de evacuación CERRADAS', 'success');
        })
        .catch(error => {
            console.error('Error al cerrar puertas:', error);
            mostrarNotificacion('❌ Error al cerrar puertas', 'error');
        });
}

// Mostrar notificaciones temporales
function mostrarNotificacion(mensaje, tipo) {
    const notif = document.createElement('div');
    notif.className = `notificacion ${tipo}`;
    notif.textContent = mensaje;
    
    document.body.appendChild(notif);
    
    setTimeout(() => {
        notif.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notif.remove(), 300);
    }, 3000);
}