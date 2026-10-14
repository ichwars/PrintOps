"""Real HTTP/engine smoke; start the built image first (no fake slicer)."""

import http.client
import io
import json
import math
import os
import re
import struct
import unittest
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

PRINTER = "Bambu Lab X1 Carbon 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL X1C"
FILAMENT = "Generic PLA"


def cube_stl():
    """Closed 10 mm cube, generated without external fixture/licensing inputs."""
    vertices = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10)]
    faces = [
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 0, 4),
        (3, 4, 7),
    ]
    data = bytearray(b"PrintOps native HTTP smoke".ljust(80, b"\0"))
    data.extend(struct.pack("<I", len(faces)))
    normals = [(0, 0, -1), (0, 0, 1), (0, -1, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0)]
    for index, face in enumerate(faces):
        points = [c for vertex in face for c in vertices[vertex]]
        data.extend(struct.pack("<12fH", *normals[index // 2], *points, 0))
    return bytes(data)


def request(method, path, body=None, headers=None):
    target = urlsplit(os.environ.get("SIDECAR_URL", "http://127.0.0.1:3003"))
    if target.scheme != "http" or target.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("Smoke tests must target a local disposable sidecar")
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=180)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


def multipart(fields, files):
    boundary = uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, filename, content_type, data in files:
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + data
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def profiles():
    return [
        ("printerProfile", {"type": "machine", "name": f"# {PRINTER}", "inherits": PRINTER, "from": "User"}),
        (
            "presetProfile",
            {
                "type": "process",
                "inherits": PROCESS,
                "from": "User",
                "wall_loops": "3",
                "curr_bed_type": "Textured PEI Plate",
            },
        ),
        ("filamentProfile", {"type": "filament", "inherits": FILAMENT, "from": "User", "nozzle_temperature": ["-1"]}),
    ]


def slice_request(export_type, *, malformed=False, renamed=False):
    files = [("file", "cube.stl", "model/stl", cube_stl())]
    for field, profile in profiles():
        if renamed and field == "printerProfile":
            profile["name"] = "PrintOps smoke custom printer"
        data = b"{invalid" if malformed and field == "filamentProfile" else json.dumps(profile).encode()
        files.append((field, f"{field}.json", "application/json", data))
    body, headers = multipart({"exportType": export_type, "plate": "1", "arrange": "true"}, files)
    return request("POST", "/slice", body, headers)


class NativeHttpSmoke(unittest.TestCase):
    def json_request(self, path, data=None):
        status, _, body = request(
            "POST" if data is not None else "GET",
            path,
            json.dumps(data).encode() if data is not None else None,
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200, body[:2000])
        return json.loads(body)

    def test_health_reports_real_pinned_engine(self):
        health = self.json_request("/health")
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["checks"]["orcaslicer"]["available"])
        self.assertEqual(health["checks"]["orcaslicer"]["version"], "2.4.2")
        print("Native engine health:", json.dumps(health), flush=True)

    def test_bundled_listing_and_inherited_profile_triplet(self):
        listing = self.json_request("/profiles/bundled")
        for slot, name in [("printer", PRINTER), ("process", PROCESS), ("filament", FILAMENT)]:
            self.assertTrue(any(p["name"] == name for p in listing[slot]), f"Missing {slot} profile: {name}")
        resolved = []
        for (_, profile), category in zip(profiles(), ["machine", "process", "filament"], strict=True):
            result = self.json_request("/profiles/resolve", {"category": category, "profile": profile})["profile"]
            self.assertFalse(result.get("inherits"))
            self.assertEqual(result["from"], "system")
            resolved.append(result)
        self.assertEqual(resolved[0]["name"], PRINTER)
        self.assertEqual(float(resolved[0]["nozzle_diameter"][0]), 0.4)
        self.assertIn("M620", resolved[0]["machine_start_gcode"])
        self.assertEqual(float(resolved[1]["layer_height"]), 0.2)
        self.assertEqual(resolved[1]["wall_loops"], "3")
        self.assertGreater(float(resolved[2]["nozzle_temperature"][0]), 0)

    def check_slice(self, export_type, *, renamed=False):
        status, headers, body = slice_request(export_type, renamed=renamed)
        self.assertEqual(status, 200, body[:2000])
        self.assertGreater(len(body), 1000)
        metadata = {}
        for name in ["x-print-time-seconds", "x-filament-used-g", "x-filament-used-mm"]:
            value = float(headers[name])
            self.assertTrue(math.isfinite(value) and value > 0, (name, value))
            metadata[name] = value
        if export_type == "3mf":
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("[Content_Types].xml", archive.namelist())
                names = [n for n in archive.namelist() if n.endswith(".gcode")]
                self.assertEqual(len(names), 1)
                gcode = archive.read(names[0]).decode()
        else:
            gcode = body.decode()
        self.assertRegex(gcode, r"(?m)^G1 .*E[0-9]")
        self.assertRegex(gcode, r"(?m)^; wall_loops = 3\s*$")
        self.assertIn("M620", gcode)
        for key, label in [("x-filament-used-g", "g"), ("x-filament-used-mm", "mm")]:
            match = re.search(r"; filament used \[" + label + r"\] =\s*([0-9.]+)", gcode)
            self.assertIsNotNone(match)
            self.assertAlmostEqual(metadata[key], float(match[1]), places=2)
        duration = re.search(r"total estimated time:\s*([^;\r\n]+)", gcode)
        self.assertIsNotNone(duration)
        seconds = sum(
            int(value) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
            for value, unit in re.findall(r"(\d+)([dhms])", duration[1])
        )
        self.assertEqual(metadata["x-print-time-seconds"], seconds)
        evidence = os.environ.get("SMOKE_EVIDENCE_DIR")
        if evidence:
            target = Path(evidence)
            target.mkdir(parents=True, exist_ok=True)
            stem = f"slice-{export_type}" + ("-renamed" if renamed else "")
            (target / f"{stem}.{export_type}").write_bytes(body)
            (target / f"{stem}-headers.json").write_text(json.dumps(headers, indent=2))
        print(f"Real {export_type} slice ({len(body)} bytes, renamed={renamed}): {metadata}", flush=True)

    def test_real_gcode_slice(self):
        self.check_slice("gcode")

    def test_real_3mf_slice(self):
        self.check_slice("3mf")

    def test_real_renamed_printer_slice(self):
        self.check_slice("gcode", renamed=True)

    def test_malformed_uploaded_json_rejected(self):
        status, _, body = slice_request("gcode", malformed=True)
        self.assertEqual(status, 400, body)
        self.assertIn("Invalid JSON", json.loads(body)["message"])

    def test_existing_four_mib_profile_limit(self):
        files = [
            ("file", "cube.stl", "model/stl", cube_stl()),
            ("filamentProfile", "filament.json", "application/json", b" " * (4 * 1024 * 1024 + 1)),
        ]
        body, headers = multipart({}, files)
        status, _, response = request("POST", "/slice", body, headers)
        self.assertEqual(status, 413, response)
        self.assertIn("4 MB", json.loads(response)["message"])

    def test_repeated_filaments_keep_existing_sixteen_part_limit(self):
        files = [("file", "cube.stl", "model/stl", cube_stl())]
        files.extend(("filamentProfile", f"filament{i}.json", "application/json", b"{}") for i in range(17))
        body, headers = multipart({}, files)
        status, _, response = request("POST", "/slice", body, headers)
        self.assertEqual(status, 400, response)
        self.assertIn("Unexpected file field", json.loads(response)["message"])

    def test_unsupported_step_upload_rejected(self):
        body, headers = multipart({}, [("file", "cube.step", "model/step", b"ISO-10303-21;")])
        status, _, response = request("POST", "/slice", body, headers)
        self.assertEqual(status, 400, response)
        self.assertIn("STEP files cannot be sliced", json.loads(response)["message"])

    def test_model_required(self):
        body, headers = multipart({"plate": "1"}, [])
        status, _, response = request("POST", "/slice", body, headers)
        self.assertEqual(status, 400, response)


if __name__ == "__main__":
    unittest.main(verbosity=2)
