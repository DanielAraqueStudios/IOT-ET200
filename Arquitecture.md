## Arquitectura de Control e IoT Industrial: PLC Siemens → OPC UA → Gateway IOT2050 → MQTT Broker en Railway

Este repositorio contiene la especificación de arquitectura de red para
la integración entre el entorno de control local de planta (OT) y el
ecosistema de microservicios en la nube (IT) desplegado en Railway.

## 📌 Visión General de la Arquitectura

Enfoque híbrido con una separación clara de responsabilidades:

1. **Zona de Control (Tiempo Real Local — OT):** la periferia
   descentralizada ET200 y la pantalla HMI se comunican con el PLC
   Maestro (S7-1500) mediante **PROFINET**. Al operar en la Capa 2 del
   modelo OSI (direcciones MAC, priorización de hardware), se garantiza
   un lazo cerrado inmune al jitter de internet, con latencias
   críticas inferiores a 2 ms. **PROFINET es exclusivo de este lazo —
   no interviene en absoluto en la capa IoT descrita abajo** (ver nota
   más abajo).
2. **Zona de Supervisión (OPC UA, local):** el PLC expone un
   **servidor OPC UA nativo** (TCP/IP ordinario, no PROFINET) sobre el
   mismo puerto Ethernet, accesible solo dentro de la red de planta.
   El PLC **nunca se conecta directamente a internet**.
3. **Zona de Gateway (SIMATIC IOT2050):** un único dispositivo, en la
   misma red plana que el PLC y el router de planta, ejecuta un
   servicio propio en **Node.js** que actúa de traductor: lee/escribe
   tags por OPC UA hacia el PLC, y publica/suscribe por MQTT hacia el
   broker en Railway.
4. **Zona de Nube (IT):** el broker MQTT en Railway recibe telemetría y
   despacha comandos; la aplicación cloud consume y escribe sobre los
   mismos topics.

### Nota importante: PROFINET no es necesario para esta capa IoT

Es una pregunta frecuente al diseñar esto: **PROFINET no tiene nada que
ver con la comunicación OPC UA/MQTT.** PROFINET es el protocolo de
tiempo real (Capa 2) que usa el lazo OT existente (ET200 + HMI ↔ CPU).
OPC UA y MQTT son protocolos TCP/IP normales — solo comparten el mismo
puerto Ethernet físico de la CPU porque PROFINET, internamente, se
construye sobre Ethernet estándar y no excluye otro tráfico en el mismo
cable. Si el gateway se conectara a una interfaz de red completamente
distinta sin ningún dispositivo PROFINET, OPC UA funcionaría
exactamente igual.

## Diagrama de Flujo de Datos

```
[ET200 Periferia]  ──(PROFINET, Capa 2, <2ms)──►  [PLC MAESTRO, S7-1500]
[HMI Pantalla]      ─────────────────────────────►        |
                                                  (OPC UA server, TCP/IP,
                                                   NO PROFINET)
                                                           |
                                                           v
                                        [SIMATIC IOT2050 — gateway propio]
                                          un solo puerto Ethernet, red plana
                                          node-opcua  : lee/escribe tags PLC
                                          mqtt.js     : publica/suscribe Railway
                                                           |
                                              (MQTT/TLS por WAN, saliente)
                                                           v
                                          [RAILWAY MQTT Broker] <--> [App Cloud]
```

El PLC **no** necesita IP estática orientada a WAN, ni "Use router", ni
DNS — todo eso solo aplicaba a la ruta alternativa descrita más abajo.
Únicamente el IOT2050 necesita salida a internet, y es una conexión
**saliente** (como cualquier cliente llegando a un sitio web) — no
requiere abrir puertos ni NAT en el router de planta.

------------------------------

## 🔌 Hardware del gateway: SIMATIC IOT2050

- Modelo confirmado por placa: `6ES7 647-0BA00-0YA2`.
- SoC ARM, Linux Debian oficialmente soportado por Siemens,
  Docker-capable.
- **Un solo puerto Ethernet** (una sola dirección MAC en la placa) — a
  diferencia de modelos anteriores (IoT2020/IoT2040) que sí tienen
  variantes con interfaces separadas, este dispositivo comparte una
  única red plana para ambos tramos (PLC y WAN). No hay separación
  física OT/IT posible en este hardware; si se quisiera aislar tráfico
  más adelante, la opción es VLANs sobre ese mismo puerto, no una
  interfaz física adicional.
- Conexión física: el único puerto Ethernet del IOT2050 se conecta al
  mismo switch que el PLC **y** a un router con salida a internet — una
  red plana, una IP en el IOT2050, un gateway por defecto.

## 🛠️ Paso 1: Configurar el servidor OPC UA en el PLC (TIA Portal)

1. Vista de Dispositivos → selecciona la CPU → Propiedades → **OPC UA**.
2. Habilita el servidor (puerto por defecto 4840). Política de
   seguridad recomendada: `Basic256Sha256` con certificado
   autofirmado — esta conexión nunca sale de la red de planta, pero
   sigue siendo buena práctica cifrarla.
3. Crea una **vista de acceso a datos OPC UA** exponiendo únicamente
   los tags que necesitan lectura/escritura remota — no la tabla de
   tags completa. Ejemplo (LAB5, `FB_Subrutinas`):
   - Lectura: `Cont_Cuadro1.CV`, `Cont_Almacen1.CV`, `Cont_Almacen2.CV`,
     `Q_Running`, `Q_AlarmFault`, `Q_AlarmSetpoint`.
   - Escritura: `SP_Count_Cuadro1`, `SP_Count_Almacen1`,
     `SP_Count_Almacen2`.
4. La CPU necesita una IP estática en la red de planta (esto es
   independiente de, y **no requiere**, los pasos de "Use
   router"/DNS de la sección "Ruta alternativa" más abajo — esos solo
   aplican si el PLC se conectara directamente a internet).

### Comandos físicos vs. remotos (sin interlock, decisión del usuario)

`I_Start`/`I_Stop` (y equivalentes en otros FBs, p. ej. `I0.5` en
`FB_ServoProfinet`) son **entradas físicas** (direcciones `%I`) — OPC UA
no puede escribir sobre una dirección de entrada física sin conflicto
con el hardware. Para permitir arranque/parada remotos sin tocar esas
direcciones, hace falta un **tag adicional** por comando (memoria `M` o
estático de DB), por ejemplo `Remote_Start`/`Remote_Stop`, combinado
con la entrada física por `OR` en la lógica del FB:

```scl
IF "I_Start" OR "Remote_Start" THEN
    #Running := TRUE;
END_IF;
```

Decisión confirmada: **sin interlock** — ambas fuentes (botonera física
y remoto) escriben a la misma lógica, "gana" quien escriba último, sin
un tag de "habilitar remoto" que bloquee una fuente sobre la otra. Esto
es un cambio pendiente de aplicar en los FBs que necesiten comando
remoto (no aplicado aún a `FB_Subrutinas.scl`/`FB_ServoProfinet` en este
commit — añadir `Remote_*` tags y el `OR` correspondiente cuando se
decida qué comandos exactos se exponen).

## 💻 Paso 2: Gateway Node.js en el IOT2050

Ver `IOT/gateway/` en este repositorio para el código y las
instrucciones de instalación/ejecución (`node-opcua` + `mqtt.js`,
servicio systemd).

Dos flujos, un solo proceso:
- **Lectura:** suscripción OPC UA a los tags expuestos → serializa a
  JSON → publica por MQTT a un topic de telemetría en Railway.
- **Escritura:** suscripción MQTT a un topic de comandos → valida/parsea
  JSON → escribe por OPC UA el tag correspondiente en el PLC.

La validación de reglas de negocio (p. ej. el tope `SP_Count_* > 15` en
`FB_Subrutinas.scl`) se mantiene en el PLC — el gateway solo valida
forma/tipo del payload, no duplica lógica de planta.

------------------------------

## 📡 Ruta alternativa: PLC publicando MQTT directamente (sin gateway)

Esta fue la primera versión de esta arquitectura, documentada aquí
como referencia/alternativa — no es la ruta elegida, porque construir
y parsear JSON a mano en SCL es tedioso y fragil comparado con hacerlo
en el gateway Node.js, y porque expone el PLC directamente a internet
(mayor superficie de ataque). Se mantiene por si en algún punto se
prefiere evitar el hardware/host adicional del gateway.

### Configuración de Red del PLC necesaria para esta ruta (no aplica a la ruta elegida)

1. Vista de Dispositivos → CPU → General → Interfaz PROFINET [X1] →
   Direcciones Ethernet. IP estática (ej. 192.168.1.50), máscara (ej.
   255.255.255.0).
2. Activa **"Use router"** con la IP del router de planta (ej.
   192.168.1.1) — sin esto el PLC no tiene ruta de salida a WAN.
3. Configuración Avanzada → Configuración DNS → agrega el router de
   planta o DNS públicos (8.8.8.8 / 1.1.1.1), ya que Railway asigna
   dominios (`*.up.railway.app`).

### El bloque `LMQTT_Client` (SCL)

Regla de oro: el dominio en `qdnsBrokerAddress` debe terminar en un
punto (`.`) o el bloque arroja el error 8601 (fallo de resolución DNS).

```scl
"LMQTT_Client_DB"(
    enable            := #connect_trigger,
    publish           := #publish_trigger,
    status            => #mqtt_status,
    qdnsBrokerAddress := 'tu-broker-id.up.railway.app.',
    // ... resto de parámetros de configuración y payload
);
```

------------------------------

## Preguntas pendientes para pulir esta configuración

- ¿Qué tags exactos (por lab/FB) se exponen para escritura remota, más
  allá del ejemplo de LAB5 arriba?
- ¿Puerto 1883 (sin cifrar) o 8883 (TLS) para la conexión MQTT del
  gateway hacia Railway? (Recomendado: 8883, ya que este tramo sí cruza
  la WAN.)
