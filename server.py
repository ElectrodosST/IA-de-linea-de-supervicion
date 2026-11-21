import argparse
import csv
import json
import mimetypes
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import cv2

import main


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "produccion"
PHOTOS = OUTPUT / "imagenes"
CSV_PATH = OUTPUT / "inspecciones.csv"


class ProductionState:
    def __init__(self, model_path):
        self.lock = threading.RLock()
        self.counts = {"BUENA": 0, "DANADA": 0, "REVISAR": 0}
        self.total = 0
        self.last = None
        self.lots = {}
        OUTPUT.mkdir(parents=True, exist_ok=True)
        PHOTOS.mkdir(parents=True, exist_ok=True)
        if not CSV_PATH.exists():
            with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as file:
                csv.writer(file).writerow(
                    ("timestamp", "lote", "pieza", "resultado", "probabilidad_danada", "motivo", "foto")
                )
        self.load_history()

    def load_history(self):
        if not CSV_PATH.exists():
            return
        with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not row:
                    continue
                timestamp = row.get("timestamp", "")
                lot_id = row.get("lote", "")
                piece_id = row.get("pieza", "")
                label = row.get("resultado", "REVISAR")
                try:
                    probability = float(row.get("probabilidad_danada", "0"))
                except ValueError:
                    probability = 0.0
                reason = row.get("motivo", "")
                photo = row.get("foto", "")
                if not timestamp or not lot_id or not piece_id:
                    continue
                date = timestamp[:10]
                lot = self.lots.setdefault(
                    lot_id,
                    self.empty_lot(lot_id, date, timestamp),
                )
                lot["piezas"].append(
                    self.piece(piece_id, lot_id, date, timestamp, label, probability, reason, photo)
                )
                lot["cantidad"] = len(lot["piezas"])
                lot["buenas"] = sum(p["resultado"] == "Buena" for p in lot["piezas"])
                lot["defectuosas"] = sum(p["resultado"] == "Defectuosa" for p in lot["piezas"])
                if label == "Defectuosa":
                    lot["byReason"][0] += 1
                self.counts["BUENA"] += label == "Buena"
                self.counts["DANADA"] += label == "Defectuosa"
                self.counts["REVISAR"] += label not in ("Buena", "Defectuosa")
                self.total += 1

    @staticmethod
    def shift(turn_hour):
        return "Matutino" if 6 <= turn_hour < 14 else "Vespertino"

    def empty_lot(self, lot_id, date, timestamp):
        hour = int(timestamp[11:13]) if len(timestamp) >= 13 else 6
        turn = self.shift(hour)
        return {
            "id": lot_id,
            "fecha": date,
            "inicio": "{:02d}:00".format(hour if turn == "Matutino" else max(hour - 8, 14)),
            "fin": "--:--",
            "turno": turn,
            "operador": "Línea automática",
            "cantidad": 0,
            "buenas": 0,
            "defectuosas": 0,
            "estado": "En curso",
            "horas": [0, 0],
            "startH": hour,
            "byReason": [0] * 5,
            "piezas": [],
        }

    @staticmethod
    def piece(piece_id, lot_id, date, timestamp, label, probability, reason, photo):
        return {
            "pieza": piece_id,
            "lote": lot_id,
            "fecha": date,
            "hora": timestamp[11:16],
            "estacion": "Camara IA",
            "operador": "Línea automática",
            "resultado": label,
            "motivo": reason or ("—" if label == "Buena" else "Defecto detectado por IA"),
            "_probabilidad": probability,
            "_foto": photo,
        }

    def get_lot(self, now):
        date = now.strftime("%Y-%m-%d")
        hour = now.hour
        turn_hour = hour
        shift_start = 6 if 6 <= hour < 14 else 14 if 14 <= hour < 22 else 22
        lot_prefix = date.replace("-", "")[-6:]
        with self.lock:
            candidates = [
                lot for lot in self.lots.values()
                if lot["fecha"] == date and lot["turno"] == self.shift(turn_hour)
                and lot["estado"] == "En curso"
            ]
            if candidates:
                lot = candidates[-1]
            else:
                number = sum(
                    lot["fecha"] == date and lot["turno"] == self.shift(turn_hour)
                    for lot in self.lots.values()
                ) + 1
                lot_id = "L-{}-{:02d}".format(lot_prefix, number)
                lot = self.empty_lot(lot_id, date, now.isoformat(timespec="seconds"))
                lot["inicio"] = "{:02d}:00".format(shift_start)
                lot["turno"] = self.shift(turn_hour)
                lot["piezas"] = []
                self.lots[lot_id] = lot
            return lot

    def record(self, label, probability, frame, threshold):
        now = datetime.now().astimezone()
        with self.lock:
            lot = self.get_lot(now)
            sequence = len(lot["piezas"]) + 1
            day_code = now.strftime("%y%m%d")
            lot_code = lot["id"].rsplit("-", 1)[-1]
            piece_id = "P-{}{}-{:03d}".format(day_code, lot_code, sequence)
            reason = "Detectado por IA" if label == "Defectuosa" else ("Sin defecto" if label == "Buena" else "Requiere revision")
            photo_name = ""
            photo_url = ""
            if frame is not None:
                photo_name = "{}_{}.jpg".format(now.strftime("%Y%m%d_%H%M%S_%f"), piece_id)
                photo_path = PHOTOS / photo_name
                cv2.imwrite(str(photo_path), frame)
                photo_url = "/produccion/imagenes/" + photo_name
            lot["cantidad"] = len(lot["piezas"]) + 1
            lot["piezas"].append(
                self.piece(
                    piece_id,
                    lot["id"],
                    now.strftime("%Y-%m-%d"),
                    now.isoformat(timespec="seconds"),
                    "Buena" if label == "BUENA" else ("Defectuosa" if label == "DANADA" else "REVISAR"),
                    probability,
                    reason,
                    photo_url,
                )
            )
            lot["buenas"] = sum(p["resultado"] == "Buena" for p in lot["piezas"])
            lot["defectuosa"] = sum(p["resultado"] == "Defectuosa" for p in lot["piezas"])
            lot["defectuosas"] = lot["defectuosa"]
            if label == "BUENA":
                self.counts["BUENA"] += 1
            elif label == "DANADA":
                self.counts["DANADA"] += 1
                reason_index = 0
                lot["byReason"][reason_index] += 1
            else:
                self.counts["REVISAR"] += 1
            self.total += 1
            self.last = {
                "pieza": piece_id,
                "lote": lot["id"],
                "resultado": "Buena" if label == "BUENA" else ("Defectuosa" if label == "DANADA" else "REVISAR"),
                "probabilidad": probability,
                "timestamp": now.isoformat(timespec="seconds"),
            }
            with CSV_PATH.open("a", newline="", encoding="utf-8-sig") as file:
                csv.writer(file).writerow(
                    (now.isoformat(timespec="seconds"), lot["id"], piece_id,
                     self.last["resultado"], "{:.6f}".format(probability), reason, photo_url)
                )
            return self.last

    def snapshot(self):
        with self.lock:
            lots = []
            for lot in sorted(self.lots.values(), key=lambda item: (item["fecha"], item["inicio"])):
                copied = dict(lot)
                copied["piezas"] = [
                    dict(piece, foto=piece["_foto"]) if "_foto" in piece else dict(piece)
                    for piece in lot["piezas"]
                ]
                lots.append(copied)
            return {
                "status": "operando",
                "counts": dict(self.counts),
                "total": self.total,
                "last": self.last,
                "lots": lots,
            }


class CameraCapture:
    def __init__(self, source):
        self.source = int(source) if source.isdigit() else source
        self.lock = threading.Lock()
        self.frame = None
        self.error = None
        self.stop_event = threading.Event()
        self.capture = cv2.VideoCapture(self.source)
        if not self.capture.isOpened():
            self.error = "No se pudo abrir la camara: {}".format(source)
        else:
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def start(self):
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while not self.stop_event.is_set():
            ok, frame = self.capture.read()
            if not ok:
                self.error = "Se perdio la lectura de la camara."
                time.sleep(0.1)
                continue
            with self.lock:
                self.frame = frame

    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.stop_event.set()
        self.capture.release()


def create_handler(state, camera):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VisionLineServer/1.0"

        def send_json(self, payload, code=200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/api/state":
                self.send_json(state.snapshot())
            elif path == "/api/status":
                self.send_json({
                    "operating": camera.error is None,
                    "error": camera.error,
                    "last": state.last,
                    "counts": state.counts,
                })
            elif path == "/api/frame":
                frame = camera.get_frame()
                if frame is None:
                    self.send_json({"error": camera.error or "Sin fotogramas"}, 503)
                    return
                ok, encoded = cv2.imencode(".jpg", frame)
                if not ok:
                    self.send_json({"error": "No se pudo codificar el fotograma"}, 500)
                    return
                body = encoded.tobytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/" or path == "/index.html":
                self.serve_file(ROOT / "index.html", "text/html")
            elif path.startswith("/produccion/imagenes/"):
                name = Path(path).name
                self.serve_file(PHOTOS / name, "image/jpeg")
            elif path.startswith("/static/"):
                self.serve_file(ROOT / path.lstrip("/"))
            else:
                self.send_json({"error": "Ruta no encontrada"}, 404)

        def do_POST(self):
            path = urlsplit(self.path).path
            if path != "/api/record":
                self.send_json({"error": "Ruta no encontrada"}, 404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json({"error": "JSON invalido"}, 400)
                return
            label = str(payload.get("label", "REVISAR")).upper()
            try:
                probability = float(payload.get("probability", 0.5))
            except (TypeError, ValueError):
                probability = 0.5
            if label not in ("BUENA", "DANADA", "REVISAR"):
                label = "REVISAR"
            probability = max(0.0, min(1.0, probability))
            result = state.record(label, probability, camera.get_frame(), float(payload.get("threshold", 0.70)))
            self.send_json(result)

        def serve_file(self, path, content_type=None):
            if not path.is_file():
                self.send_json({"error": "Archivo no encontrado"}, 404)
                return
            body = path.read_bytes()
            if content_type is None:
                content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format_string, *args):
            return

    return Handler


def run_detection(state, camera, classifier, threshold, cooldown, motion_threshold):
    previous = None
    motion_seen = False
    motion_quiet_frames = 0
    last_record = 0.0
    while not camera.stop_event.is_set():
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180))
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        if previous is None:
            previous = gray
        difference = cv2.absdiff(previous, gray)
        moving = float((difference > motion_threshold).mean())
        previous = cv2.addWeighted(previous, 0.96, gray, 0.04, 0)
        now = time.monotonic()
        if moving > 0.015:
            motion_seen = True
            motion_quiet_frames = 0
        else:
            if motion_seen:
                motion_quiet_frames += 1
        if motion_seen and motion_quiet_frames >= 4 and now - last_record >= cooldown:
            if classifier is not None:
                label, probability = main.classify_image(classifier, frame, threshold)
            else:
                label, probability = "REVISAR", 0.5
            state.record(label, probability, frame, threshold)
            last_record = now
            motion_seen = False
            motion_quiet_frames = 0
        time.sleep(0.08)


def build_parser():
    parser = argparse.ArgumentParser(description="Servidor local de VisionLine")
    parser.add_argument("--source", default="0", help="indice de webcam o URL RTSP")
    parser.add_argument("--model", default="modelo.joblib")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument("--cooldown", type=float, default=1.5, help="segundos entre piezas")
    parser.add_argument("--motion-threshold", type=int, default=18)
    return parser


def main_server():
    args = build_parser().parse_args()
    if not 0.5 <= args.threshold < 1:
        raise SystemExit("El umbral debe estar entre 0.5 y 1.")
    state = ProductionState(args.model)
    try:
        classifier = main.load_model(args.model)
    except (FileNotFoundError, ValueError):
        classifier = None
        print("Aviso: no hay modelo valido '{}'; las detecciones quedaran como REVISAR.".format(args.model))
    camera = CameraCapture(args.source)
    if camera.error:
        raise SystemExit(camera.error)
    camera.start()
    threading.Thread(
        target=run_detection,
        args=(state, camera, classifier, args.threshold, args.cooldown, args.motion_threshold),
        daemon=True,
    ).start()
    handler = create_handler(state, camera)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print("VisionLine: http://{}:{}/".format(args.host, args.port))
    print("Camara: {}".format(args.source))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        camera.stop()


if __name__ == "__main__":
    main_server()
