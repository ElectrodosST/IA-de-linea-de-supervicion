# VisionLine

## Ventajas

- Inspecciona piezas desde una webcam o una camara IP/RTSP.
- Guarda cada deteccion con fecha, lote, pieza y foto.
- Muestra los resultados en una pagina web con registros y graficas.
- Funciona localmente; las imagenes no se envian a un servicio externo.
- Permite marcar como **REVISAR** los casos inciertos.

## Desventajas

- Necesita fotos etiquetadas de piezas buenas y dañadas para entrenar el modelo.
- La precision depende de la calidad y variedad de esas fotos, la iluminacion y la posicion de la camara.
- El detector de paso usa cambios de movimiento; puede omitir o duplicar piezas si la camara esta movida, hay cambios de luz o las piezas pasan muy juntas.
- No controla maquinaria ni reemplaza una inspeccion o sistema de seguridad industrial.

## Como usarlo

### 1. Instalar dependencias (una sola vez)

Abre PowerShell en la carpeta del proyecto. Si ya tienes Python instalado en la ruta habitual de Python 3.12:

```powershell
$python = "$env:LocalAppData\Programs\Python\Python312\python.exe"
& $python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si Python no esta instalado, instala Python 3.12 y vuelve a abrir PowerShell. No pegues el texto `>>`; ejecuta cada comando en una linea separada.

### 2. Preparar fotos y entrenar

Crea estas carpetas y agrega fotos propias de las piezas:

```text
datos\
  buena\
  dañada\
```

Guarda al menos dos imagenes legibles en cada carpeta; se recomiendan muchas mas y en condiciones parecidas a las de la camara de inspeccion. Entrena el modelo:

```powershell
.\.venv\Scripts\python.exe main.py train --data datos --model modelo.joblib
```

### 3. Iniciar la inspeccion y abrir el panel

Conecta la webcam y ejecuta:

```powershell
.\.venv\Scripts\python.exe server.py --source 0 --model modelo.joblib
```

Abre `http://127.0.0.1:8080/` en el navegador. Para usar una camara IP, reemplaza `0` por la URL RTSP entre comillas:

```powershell
.\.venv\Scripts\python.exe server.py --source "rtsp://usuario:contrasena@DIRECCION/stream" --model modelo.joblib
```

La URL RTSP tiene esta forma:

```text
rtsp://USUARIO:CONTRASENA@IP_DE_LA_CAMARA:PUERTO/RUTA_DEL_VIDEO
```

- `rtsp://`: indica que se usara el protocolo RTSP.
- `USUARIO` y `CONTRASENA`: credenciales configuradas para ver el video de la camara.
- `IP_DE_LA_CAMARA`: direccion IP de la camara en la red local, por ejemplo `192.168.1.50`.
- `PUERTO`: puerto RTSP de la camara; con frecuencia es `554`, pero puede ser diferente.
- `RUTA_DEL_VIDEO`: ruta exacta del stream, que depende de la marca y la configuracion de la camara. Consultala en sus ajustes o manual.

Ejemplo de formato (datos ficticios; no lo copies sin reemplazar los valores):

```powershell
.\.venv\Scripts\python.exe server.py --source "rtsp://operador:MI_CLAVE@192.168.1.50:554/stream1" --model modelo.joblib
```

Reemplaza usuario, clave, IP, puerto y ruta por los datos reales; conserva las comillas y ejecuta el comando en una sola linea. La computadora y la camara deben poder comunicarse por la red. Si la clave contiene caracteres especiales como `@`, `:`, `/` o `#`, codificalos para URL (por ejemplo, `@` se escribe `%40`). No compartas ni publiques la URL completa: contiene credenciales de la camara.

El panel muestra las piezas detectadas y sus lotes; los registros y las fotos se guardan en `produccion\`. Detén el servidor con **Ctrl+C** en PowerShell. Si no existe un modelo entrenado, las detecciones se muestran como **REVISAR**.
