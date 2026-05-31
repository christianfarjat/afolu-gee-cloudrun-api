"""Verificacion local de los servicios de tiers de ForestScan.

No requiere credenciales de GEE: inyecta modulos falsos `ee` y
`google.cloud.secretmanager` para que initialize_ee() tenga exito al importar,
y luego ejercita las rutas reales de cada servicio con el test_client de Flask.

El fake de `ee` simula lo justo para que la logica de cada handler corra:
encadenamiento de operaciones de imagen, ee.Image.pixelArea, reductores y
reduceRegion (incluyendo el group reducer de EUDR).
"""

import sys
import types
import importlib.util
import os


# ---------------------------------------------------------------------------
# Fakes de Earth Engine
# ---------------------------------------------------------------------------
class _FakeNumber:
    """Simula ee.Number / Geometry.area().divide(n).getInfo()."""
    def __init__(self, value):
        self.value = value

    def divide(self, n):
        return _FakeNumber(self.value / n)

    def getInfo(self):
        return self.value


class _FakeReducer:
    def __init__(self, grouped=False):
        self.grouped = grouped

    def group(self, **kwargs):
        return _FakeReducer(grouped=True)


class _FakeReduceResult:
    """Resultado de reduceRegion; getInfo() devuelve datos de muestra."""
    def __init__(self, grouped):
        self.grouped = grouped

    def getInfo(self):
        if self.grouped:
            # Deforestacion post-corte repartida en 2021 y 2022.
            return {'groups': [
                {'year_code': 21, 'sum': 3.5},
                {'year_code': 22, 'sum': 1.5},
            ]}
        # Baseline de bosque y deforestacion total post-corte.
        return {
            'forest_baseline_ha': 120.3,
            'deforestation_after_cutoff_ha': 5.0,
        }


class _FakeImage:
    """Imagen encadenable; cualquier operacion devuelve otra _FakeImage."""
    def __init__(self, *args, **kwargs):
        pass

    @staticmethod
    def pixelArea():
        return _FakeImage()

    def reduceRegion(self, reducer=None, **kwargs):
        grouped = getattr(reducer, 'grouped', False)
        return _FakeReduceResult(grouped)

    def __getattr__(self, name):
        # select, gte, And, Or, eq, gt, multiply, divide, rename,
        # updateMask, addBands, clip, ... -> encadenan.
        def _chain(*args, **kwargs):
            return self
        return _chain


class _FakeGeometry:
    def __init__(self, *args, **kwargs):
        pass

    def area(self):
        # 1.505e6 m2 -> 150.5 ha tras divide(10000)
        return _FakeNumber(1_505_000.0)


def _install_fakes():
    ee = types.ModuleType("ee")
    ee.Geometry = _FakeGeometry
    ee.Image = _FakeImage
    ee.Reducer = types.SimpleNamespace(sum=lambda: _FakeReducer())
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
# Validadores del POST valido por tier
# ---------------------------------------------------------------------------
def _check_skeleton(body):
    return body.get("status") == "skeleton" and body.get("area_ha") == 150.5


def _check_eudr(body):
    return (
        body.get("status") == "ok"
        and body.get("area_ha") == 150.5
        and body.get("forest_baseline_ha") == 120.3
        and body.get("deforestation_after_cutoff_ha") == 5.0
        and body.get("compliant") is False
        and body.get("deforestation_by_year_ha") == {"2021": 3.5, "2022": 1.5}
    )


SAMPLE_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-84.0, 10.0], [-83.9, 10.0], [-83.9, 10.1], [-84.0, 10.1], [-84.0, 10.0]]],
}

# (carpeta, endpoint, service_name, payload_valido, validador, label_post)
TIERS = [
    ("land-screening", "/land-screening", "forestscan-land-screening",
     {"geometry": SAMPLE_GEOMETRY, "year": 2023}, _check_skeleton,
     "POST valido -> 200 + skeleton + area_ha=150.5"),
    ("eudr", "/eudr-check", "forestscan-eudr",
     {"geometry": SAMPLE_GEOMETRY, "commodity": "cattle"}, _check_eudr,
     "POST valido -> 200 + compliant=False + 5.0 ha post-corte + desglose por anio"),
    ("land-planning", "/land-planning", "forestscan-land-planning",
     {"geometry": SAMPLE_GEOMETRY, "objective": "restoration"}, _check_skeleton,
     "POST valido -> 200 + skeleton + area_ha=150.5"),
]


def main():
    _install_fakes()
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    all_ok = True

    for folder, endpoint, service_name, payload, validate, post_label in TIERS:
        print(f"\n=== {service_name} ({folder}{endpoint}) ===")
        app = _load_app(os.path.join(repo_root, folder, "main.py"))
        client = app.test_client()

        checks = []

        r = client.get("/health")
        ok = r.status_code == 200 and r.get_json().get("service") == service_name
        checks.append(("GET /health -> 200 + service", ok))

        r = client.get("/")
        ok = r.status_code == 200 and endpoint in r.get_json().get("endpoints", {})
        checks.append(("GET / -> 200 + endpoint listado", ok))

        r = client.post(endpoint, json={})
        ok = r.status_code == 400 and "geometry" in r.get_json().get("error", "")
        checks.append(("POST sin geometry -> 400", ok))

        r = client.post(endpoint, json=payload)
        ok = r.status_code == 200 and validate(r.get_json())
        checks.append((post_label, ok))

        for name, passed in checks:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}")
            all_ok = all_ok and passed

    print("\n" + "=" * 50)
    print("RESULTADO:", "TODOS OK" if all_ok else "HAY FALLOS")
    print("=" * 50)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
