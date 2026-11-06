"""The About page's data (GET /about), the owner contact setting and the app version."""
import json
import re
import tomllib
from pathlib import Path

import pytest
from conftest import make_user, session_client

from server import version

ROOT = Path(__file__).resolve().parents[1]


def test_version_matches_pyproject_and_newest_changelog_release():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    releases = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(), re.M)
    assert releases, "CHANGELOG.md has no release headings"
    assert version.__version__ == pyproject == releases[0]


def test_user_agent_and_openapi_carry_the_version(app):
    assert app.USER_AGENT == f"speaker-service/{version.__version__}"
    assert app.app.version == version.__version__


def test_about_signed_out_has_only_app_info(anon, app):
    app.settings.owner_contact = "it@example.com"
    r = anon.get("/about")
    assert r.status_code == 200
    assert r.json() == {"version": version.__version__, "build": app.static_build.id}
    assert re.fullmatch(r"[0-9a-f]{12}", r.json()["build"])


@pytest.mark.parametrize("role", ["viewer", "operator", "admin"])
def test_about_signed_in_shows_this_server(app, role):
    app.settings.owner_contact = "LINE: @example"
    c = session_client(make_user(f"{role}-user", role))
    server = c.get("/about").json()["server"]
    assert server == {"speaker": app.settings.speaker_name, "transport": "cast", "owner_contact": "LINE: @example"}


def test_about_never_shows_addresses_or_secrets(client, app):
    app.settings.public_base_url = "https://speaker.example.com"
    text = client.get("/about").text
    for secret in (app.settings.api_token, app.settings.speaker_ip, "speaker.example.com"):
        assert secret not in text


def test_owner_contact_is_cleaned(app):
    assert app.Settings().owner_contact is None
    assert app.Settings(owner_contact="  it@example.com \n").owner_contact == "it@example.com"
    assert app.Settings(owner_contact="   ").owner_contact is None
    assert len(app.Settings(owner_contact="x" * 120).owner_contact) == 120
    with pytest.raises(ValueError, match="owner_contact must be at most 120 characters"):
        app.Settings(owner_contact="x" * 121)


def test_owner_contact_saved_through_settings(client, app):
    r = client.post("/settings", json={"owner_contact": " Ask Dana, it@example.com "})
    assert r.status_code == 200 and r.json()["settings"]["owner_contact"] == "Ask Dana, it@example.com"
    assert json.loads(app.CONFIG_PATH.read_text())["owner_contact"] == "Ask Dana, it@example.com"
    assert client.get("/about").json()["server"]["owner_contact"] == "Ask Dana, it@example.com"
    r = client.post("/settings", json={"owner_contact": ""})
    assert r.status_code == 200 and r.json()["settings"]["owner_contact"] is None
    r = client.post("/settings", json={"owner_contact": "x" * 200})
    assert r.status_code == 422 and r.json()["detail"] == "owner_contact must be at most 120 characters"


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_only_owners_change_the_owner_contact(app, role):
    c = session_client(make_user(f"{role}-user", role))
    assert c.post("/settings", json={"owner_contact": "me@example.com"}).status_code == 403
    assert app.settings.owner_contact is None


def test_licenses_data_is_complete():
    """static/licenses.json (the Licenses page) lists every runtime requirement, each with a license and a link."""
    data = json.loads((ROOT / "static" / "licenses.json").read_text())
    names = [p["name"] for g in data["groups"] for p in g["items"]]
    assert len(names) == len(set(names))
    for g in data["groups"]:
        for p in g["items"]:
            assert p["license"] and p["url"].startswith("https://"), p["name"]
            if p.get("text"):
                assert (ROOT / "static" / p["text"]).is_file(), p["text"]
    # every runtime requirement is listed
    reqs = [r.strip() for r in (ROOT / "requirements.txt").read_text().splitlines()]
    wanted = {re.split(r"[\[<>=~ ;]", r, maxsplit=1)[0].lower() for r in reqs if r and not r.startswith("#")}
    assert wanted <= {n.lower() for n in names}
    # the app's own license text is the repo's LICENSE
    assert (ROOT / "static" / data["app"]["text"]).read_text() == (ROOT / "LICENSE").read_text()
