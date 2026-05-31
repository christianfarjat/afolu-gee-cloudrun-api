"""Verificacion local de los esqueletos de tiers de ForestScan.

No requiere credenciales de GEE: inyecta modulos falsos `ee` y
`google.cloud.secretmanager` para que initialize_ee() tenga exito al importar,
y luego ejercita las rutas reales de cada servicio con el test_client de Flask.
"""

import sys
import types
import importlib.util
import os


# ---------------------------------------------------------------------------
# Fakes: ee + google.cloud.secretmanager
# ---------------------------------------------------------------------------
class _FakeNumber:
    """Simula el encadenamiento ee.Geometry(...).area().divide(n).getInfo()."""
    def __init__(self, value):
        self.value = value

    def divide(self, n):
        return _FakeNumber(self.value / n)

    def getInfo(self):
        return self.value


class _FakeGeometry:
    def __init__(self, *args, **kwargs):
        pass

    def area(self):
        # 1.505e6 m2 -> 150.5 ha tras divide(10000)
        return _FakeNumber(1_505_000.0)


def _install_fakes():
    ee = types.ModuleType("ee")
    ee.Geometry = _FakeGeometry
    ee.EEException = type("EEException", (Exception,), {})
    ee.Initialize = lambda *a, **k: None  # exito inmediato
    ee.ServiceAccountCredentials = lambda *a, **k: None
    sys.modules["ee"] = ee

    google = sys.modules.get("google") or types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    secretmanager = types.ModuleType("google.cloud.secretmanager")
    secretmanager.SecretManagerServiceClient = object
    google.cloud = cloud
    cloud.secretmanager = secretmanager
    sys.modules["google"] = google
    sys.modules["google.cloud"] = cloud
    sys.modules["google.cloud.secretmanager"] = secretmanager


def _load_app(path):
    """Importa un main.py aislado y devuelve su objeto Flask `app`."""
    spec = importlib.util.spec_from_file_location(
        f"tier_{abs(hash(path))}", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


# ---------------------------------------------------------------------------
# Casos por tier: (carpeta, endpoint, service_name, payload_valido)
# ---------------------------------------------------------------------------
SAMPLE_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-84.0, 10.0], [-83.9, 10.0], [-83.9, 10.1], [-84.0, 10.1], [-84.0, 10.0]]],
}

TIERS = [
    ("land-screening", "/land-screening", "forestscan-land-screening",
     {"geometry": SAMPLE_GEOMETRY, "year": 2023}),
    ("eudr", "/eudr-check", "forestscan-eudr",
     {"geometry": SAMPLE_GEOMETRY, "commodity": "cattle"}),
    ("land-planning", "/land-planning", "forestscan-land-planning",
     {"geometry": SAMPLE_GEOMETRY, "objective": "restoration"}),
]


def main():
    _install_fakes()
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    all_ok = True

    for folder, endpoint, service_name, payload in TIERS:
        print(f"\n=== {service_name} ({folder}{endpoint}) ===")
        app = _load_app(os.path.join(repo_root, folder, "main.py"))
        client = app.test_client()

        checks = []

        # 1) /health
        r = client.get("/health")
        ok = r.status_code == 200 and r.get_json().get("service") == service_name
        checks.append(("GET /health -> 200 + service", ok))

        # 2) /
        r = client.get("/")
        ok = r.status_code == 200 and endpoint in r.get_json().get("endpoints", {})
        checks.append(("GET / -> 200 + endpoint listado", ok))

        # 3) endpoint principal sin geometry -> 400
        r = client.post(endpoint, json={})
        ok = r.status_code == 400 and "geometry" in r.get_json().get("error", "")
        checks.append(("POST sin geometry -> 400", ok))

        # 4) endpoint principal con payload valido -> 200 + skeleton
        r = client.post(endpoint, json=payload)
        body = r.get_json()
        ok = (
            r.status_code == 200
            and body.get("status") == "skeleton"
            and body.get("area_ha") == 150.5
        )
        checks.append(("POST valido -> 200 + skeleton + area_ha=150.5", ok))

        for name, passed in checks:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}")
            all_ok = all_ok and passed

    print("\n" + "=" * 50)
    print("RESULTADO:", "TODOS OK" if all_ok else "HAY FALLOS")
    print("=" * 50)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
