// Código para comunicarse con Flask vía Serial

const int ledPin = 13;  // LED integrado
String input = "";

void setup() {
  pinMode(ledPin, OUTPUT);
  Serial.begin(9600);
  Serial.println("Arduino listo");
}

void loop() {
  // Enviar lecturas simuladas cada segundo
  Serial.print("Lectura del sensor: ");
  Serial.println(analogRead(A0));  // Ejemplo: lee A0

  // Leer si hay datos desde Python
  if (Serial.available() > 0) {
    char c = Serial.read();

    if (c == 'L') {
      digitalWrite(ledPin, HIGH);
      Serial.println("LED encendido");
    } 
    else if (c == 'l') {
      digitalWrite(ledPin, LOW);
      Serial.println("LED apagado");
    }
  }

  delay(1000); // Espera un segundo antes de enviar nueva lectura
}
