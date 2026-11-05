"""static/licenses.json and static/licenses/*.txt (made by scripts/gen_licenses.py) agree with each other and with
requirements.txt. Needs no virtualenv: it only reads the committed files."""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
DEV_TOOLS = {"pytest", "ruff"}


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def load():
    return json.loads((STATIC / "licenses.json").read_text(encoding="utf-8"))


def items(data):
    return [p for g in data["groups"] for p in g["items"]]


def test_every_named_text_file_exists():
    data = load()
    for path in [data["app"]["text"]] + [p["text"] for p in items(data) if p.get("text")]:
        assert (STATIC / path).is_file(), path


def test_no_orphan_license_files():
    data = load()
    named = {data["app"]["text"]} | {p["text"] for p in items(data) if p.get("text")}
    on_disk = {f"licenses/{f.name}" for f in (STATIC / "licenses").iterdir()}
    assert on_disk - named == set()


def test_every_runtime_requirement_is_in_the_server_group():
    server = next(g for g in load()["groups"] if g["id"] == "server")
    listed = {norm(p["name"]) for p in server["items"]}
    reqs = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            reqs.append(norm(re.split(r"[\[<>=!~ ;]", line, maxsplit=1)[0]))
    reqs = [r for r in reqs if r not in DEV_TOOLS]
    assert reqs, "requirements.txt has no requirements"
    assert set(reqs) - listed == set()


def test_generator_lists_the_same_python_packages():
    """scripts/gen_licenses.py's package table is what the committed licenses.json lists, in the same order."""
    spec = importlib.util.spec_from_file_location("gen_licenses", ROOT / "scripts" / "gen_licenses.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    server = next(g for g in load()["groups"] if g["id"] == "server")
    python_pkgs = [p for p in server["items"] if p.get("kind") != "program" and p["name"] != "Python"]
    assert [(p["name"], p["license"], p["url"]) for p in python_pkgs] == [(n, lic, u) for n, _, lic, u in gen.PY]
    for p in python_pkgs:
        assert p["text"] == f"licenses/{gen.slug(p['name'])}.txt"
