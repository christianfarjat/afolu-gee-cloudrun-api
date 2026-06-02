"""Verificacion local de los servicios de tiers de ForestScan.

No requiere credenciales de GEE: inyecta modulos falsos `ee` y
`google.cloud.secretmanager` para que initialize_ee() tenga exito al importar,
y luego ejercita las rutas reales de cada servicio con el test_client de Flask.

El fake de `ee` simula lo justo para que la logica de cada handler corra:
encadenamiento de operaciones de imagen, ImageCollection, Terrain.slope,
reductores (sum / mean / frequencyHistogram / group) y reduceRegion.
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
    def __init__(self, kind="sum", grouped=False):
        self.kind = kind
        self.grouped = grouped

    def group(self, **kwargs):
        return _FakeReducer(kind=self.kind, grouped=True)


# Valores de muestra que devuelve reduceRegion segun la banda solicitada.
_KNOWN_BANDS = {
    # EUDR
    "forest_baseline_ha": 120.3,
    "deforestation_after_cutoff_ha": 5.0,
    # Land screening
    "recent_loss_ha": 30.0,
    # Land planning
    "suitable_ha": 90.0,
    "restricted_ha": 30.0,
    "excluded_ha": 30.0,
    "slope": 12.5,
}


class _FakeStats(dict):
    """Resultado de reduceRegion().getInfo() con .get() parametrizado."""
    def __init__(self, kind, grouped):
        super().__init__()
        self._kind = kind
        self._grouped = grouped

    def getInfo(self):
        return self

    def get(self, key, default=None):
        if self._grouped and key == "groups":
            return [
                {"year_code": 21, "sum": 3.5},
                {"year_code": 22, "sum": 1.5},
            ]
        if self._kind == "freq" and key == "Map":
            # 1000 px: 80% tree, 15% grassland, 5% cropland.
            return {"10": 800, "30": 150, "40": 50}
        if key in _KNOWN_BANDS:
            return _KNOWN_BANDS[key]
        return default


class _FakeImage:
    """Imagen encadenable; cualquier operacion devuelve otra _FakeImage."""
    def __init__(self, *args, **kwargs):
        pass

    @staticmethod
    def pixelArea():
        return _FakeImage()

    def reduceRegion(self, reducer=None, **kwargs):
        kind = getattr(reducer, "kind", "sum")
        grouped = getattr(reducer, "grouped", False)
        return _FakeStats(kind, grouped)

    def __getattr__(self, name):
        # select, gte, gt, lt, eq, And, Or, Not, multiply, divide, rename,
        # updateMask, addBands, clip, first, filter*, ... -> encadenan.
        def _chain(*args, **kwargs):
            return self
        return _chain


class _FakeImageCollection(_FakeImage):
    def __init__(self, *args, **kwargs):
        pass

    def first(self):
        return _FakeImage()


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
    ee.ImageCollection = _FakeImageCollection
    ee.Terrain = types.SimpleNamespace(slope=lambda img: _FakeImage())
    ee.Reducer = types.SimpleNamespace(
        sum=lambda: _FakeReducer("sum"),
        mean=lambda: _FakeReducer("mean"),
        frequencyHistogram=lambda: _FakeReducer("freq"),
    )
    ee.EEException = type("EEException", (Exception,), {})
    ee.Initialize = lambda *a, **k: None
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
    """Importa un main.py aislado y devuelve su objeto Flask `app`.

    Inserta la carpeta del tier en sys.path para que resuelva `import auth`,
    y limpia el modulo `auth` cacheado entre tiers (cada tier tiene el suyo).
    """
    folder = os.path.dirname(path)
    sys.modules.pop("auth", None)
    sys.path.insert(0, folder)
    try:
        spec = importlib.util.spec_from_file_location(
            f"tier_{abs(hash(path))}", path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    finally:
        if sys.path and sys.path[0] == folder:
            sys.path.pop(0)


# Headers que IAP inyecta tras autenticar al usuario.
VALID_USER = "christian.farjat@mjmenergia.com"
AUTH_HEADERS = {"X-Goog-Authenticated-User-Email": f"accounts.google.com:{VALID_USER}"}
WRONG_DOMAIN_HEADERS = {
    "X-Goog-Authenticated-User-Email": "accounts.google.com:hacker@gmail.com"
}


# ---------------------------------------------------------------------------
# Validadores del POST valido por tier
# ---------------------------------------------------------------------------
def _check_screening(body):
    return (
        body.get("status") == "ok"
        and body.get("area_ha") == 150.5
        and body.get("dominant_class") == "tree_cover"
        and body.get("tree_cover_pct") == 80.0
        and body.get("recent_forest_loss_ha") == 30.0
        and body.get("deforestation_risk") == "high"
    )


def _check_eudr(body):
    return (
        body.get("status") == "ok"
        and body.get("area_ha") == 150.5
        and body.get("forest_baseline_ha") == 120.3
        and body.get("deforestation_after_cutoff_ha") == 5.0
        and body.get("compliant") is False
        and body.get("deforestation_by_year_ha") == {"2021": 3.5, "2022": 1.5}
    )


def _check_planning(body):
    zones = body.get("zones", [])
    return (
        body.get("status") == "ok"
        and body.get("area_ha") == 150.5
        and body.get("mean_slope_deg") == 12.5
        and len(zones) == 3
        and {z["zone"] for z in zones} == {"suitable", "restricted", "excluded"}
    )


SAMPLE_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-84.0, 10.0], [-83.9, 10.0], [-83.9, 10.1], [-84.0, 10.1], [-84.0, 10.0]]],
}

# (carpeta, endpoint, service_name, payload_valido, validador, label_post)
TIERS = [
    ("land-screening", "/land-screening", "forestscan-land-screening",
     {"geometry": SAMPLE_GEOMETRY, "year": 2023}, _check_screening,
     "POST valido -> 200 + dominant=tree_cover + tree 80% + riesgo=high"),
    ("eudr", "/eudr-check", "forestscan-eudr",
     {"geometry": SAMPLE_GEOMETRY, "commodity": "cattle"}, _check_eudr,
     "POST valido -> 200 + compliant=False + 5.0 ha post-corte + desglose por anio"),
    ("land-planning", "/land-planning", "forestscan-land-planning",
     {"geometry": SAMPLE_GEOMETRY, "objective": "restoration"}, _check_planning,
     "POST valido -> 200 + 3 zonas (suitable/restricted/excluded) + pendiente media"),
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
        checks.append(("GET /health -> 200 + service (publico)", ok))

        r = client.get("/")
        ok = r.status_code == 200 and endpoint in r.get_json().get("endpoints", {})
        checks.append(("GET / -> 200 + endpoint listado (publico)", ok))

        # --- Autenticacion Google / IAP ---
        r = client.post(endpoint, json=payload)  # sin header de IAP
        ok = r.status_code == 401
        checks.append(("POST sin auth -> 401", ok))

        r = client.post(endpoint, json=payload, headers=WRONG_DOMAIN_HEADERS)
        ok = r.status_code == 403
        checks.append(("POST dominio no autorizado -> 403", ok))

        r = client.get("/whoami", headers=AUTH_HEADERS)
        ok = r.status_code == 200 and r.get_json().get("authenticated_user") == VALID_USER
        checks.append(("GET /whoami con auth -> 200 + usuario", ok))

        # --- Logica del tier (autenticado) ---
        r = client.post(endpoint, json={}, headers=AUTH_HEADERS)
        ok = r.status_code == 400 and "geometry" in r.get_json().get("error", "")
        checks.append(("POST auth sin geometry -> 400", ok))

        r = client.post(endpoint, json=payload, headers=AUTH_HEADERS)
        body = r.get_json()
        ok = (
            r.status_code == 200
            and validate(body)
            and body.get("authenticated_user") == VALID_USER
        )
        checks.append((post_label + " + authenticated_user", ok))

        for name, passed in checks:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}")
            all_ok = all_ok and passed

    print("\n" + "=" * 50)
    print("RESULTADO:", "TODOS OK" if all_ok else "HAY FALLOS")
    print("=" * 50)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
