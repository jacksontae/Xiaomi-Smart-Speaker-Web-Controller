"""Regenerate static/licenses.json and static/licenses/*.txt (the Licenses page).

Usage:
    python scripts/gen_licenses.py --venv .venv \\
        [--libdeps firmware/.pio/libdeps/esp32dev] \\
        [--esp-core ~/.platformio/packages/framework-arduinoespressif8266] [--out static]

--venv is a virtualenv holding exactly requirements.txt (pip install -r requirements.txt), so the versions and
license files come from the packages the server really runs; --site-packages points at a site-packages
directory instead. The Python license is read from that venv's standard library (--python-license overrides it).
--libdeps is the firmware's PlatformIO library folder (after `pio run` in firmware/) and --esp-core a PlatformIO
Arduino core package, for its LGPL text. The output depends only on those inputs, so running it twice gives the
same files. tests/test_licenses.py checks that the result matches requirements.txt; when a dependency is added,
add it to PY below with its SPDX license and home page.
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/jacksontae/Xiaomi-Smart-Speaker-Web-Controller"

# name, dist-info prefix, SPDX license, home page — in the order the Licenses page lists them
PY = [
    ("fastapi", "fastapi", "MIT", "https://github.com/fastapi/fastapi"),
    ("starlette", "starlette", "BSD-3-Clause", "https://github.com/Kludex/starlette"),
    ("annotated-doc", "annotated_doc", "MIT", "https://github.com/fastapi/annotated-doc"),
    ("opentelemetry-api", "opentelemetry_api", "Apache-2.0", "https://github.com/open-telemetry/opentelemetry-python"),
    ("uvicorn", "uvicorn", "BSD-3-Clause", "https://uvicorn.dev/"),
    ("click", "click", "BSD-3-Clause", "https://click.palletsprojects.com/"),
    ("h11", "h11", "MIT", "https://github.com/python-hyper/h11"),
    ("websockets", "websockets", "BSD-3-Clause", "https://github.com/python-websockets/websockets"),
    ("httpx", "httpx", "BSD-3-Clause", "https://www.python-httpx.org"),
    ("httpcore", "httpcore", "BSD-3-Clause", "https://www.encode.io/httpcore"),
    ("anyio", "anyio", "MIT", "https://anyio.readthedocs.io/"),
    ("idna", "idna", "BSD-3-Clause", "https://github.com/kjd/idna"),
    ("certifi", "certifi", "MPL-2.0", "https://github.com/certifi/python-certifi"),
    ("pydantic", "pydantic", "MIT", "https://github.com/pydantic/pydantic"),
    ("pydantic_core", "pydantic_core", "MIT", "https://github.com/pydantic/pydantic"),
    ("annotated-types", "annotated_types", "MIT", "https://github.com/annotated-types/annotated-types"),
    ("typing-inspection", "typing_inspection", "MIT", "https://github.com/pydantic/typing-inspection"),
    ("typing_extensions", "typing_extensions", "PSF-2.0", "https://typing-extensions.readthedocs.io/"),
    ("PyChromecast", "pychromecast", "MIT", "https://github.com/home-assistant-libs/pychromecast"),
    ("casttube", "casttube", "MIT", "https://github.com/ur1katz/casttube"),
    ("protobuf", "protobuf", "BSD-3-Clause", "https://developers.google.com/protocol-buffers/"),
    ("zeroconf", "zeroconf", "LGPL-2.1-or-later", "https://python-zeroconf.readthedocs.io"),
    ("ifaddr", "ifaddr", "MIT", "https://github.com/pydron/ifaddr"),
    ("paho-mqtt", "paho_mqtt", "EPL-2.0 OR BSD-3-Clause", "https://eclipse.dev/paho/"),
    ("yt-dlp", "yt_dlp", "Unlicense", "https://github.com/yt-dlp/yt-dlp"),
    ("yt-dlp-ejs", "yt_dlp_ejs", "Unlicense AND MIT AND ISC", "https://github.com/yt-dlp/ejs"),
    ("brotli", "brotli", "MIT", "https://github.com/google/brotli"),
    ("mutagen", "mutagen", "GPL-2.0-or-later", "https://mutagen.readthedocs.io"),
    ("pycryptodomex", "pycryptodomex", "BSD-2-Clause", "https://www.pycryptodome.org"),
    ("requests", "requests", "Apache-2.0", "https://requests.readthedocs.io"),
    ("urllib3", "urllib3", "MIT", "https://urllib3.readthedocs.io"),
    ("charset-normalizer", "charset_normalizer", "MIT", "https://charset-normalizer.readthedocs.io/"),
    ("PyJWT", "pyjwt", "MIT", "https://github.com/jpadilla/pyjwt"),
    ("cryptography", "cryptography", "Apache-2.0 OR BSD-3-Clause", "https://cryptography.io/"),
    ("cffi", "cffi", "MIT-0", "https://cffi.readthedocs.io/"),
    ("pycparser", "pycparser", "BSD-3-Clause", "https://github.com/eliben/pycparser"),
    ("webauthn", "webauthn", "BSD-3-Clause", "https://github.com/duo-labs/py_webauthn"),
    ("cbor2", "cbor2", "MIT", "https://github.com/agronholm/cbor2"),
    ("pyOpenSSL", "pyopenssl", "Apache-2.0", "https://pyopenssl.org/"),
    ("pyasn1", "pyasn1", "BSD-2-Clause", "https://github.com/pyasn1/pyasn1"),
    ("pyasn1_modules", "pyasn1_modules", "BSD-2-Clause", "https://github.com/pyasn1/pyasn1-modules"),
]
EDL = """==> edl-v10 <==

Eclipse Distribution License - v 1.0

Copyright (c) 2007, Eclipse Foundation, Inc. and its licensors.

All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
following conditions are met:

  Redistributions of source code must retain the above copyright notice, this list of conditions and the following
  disclaimer.
  Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
  disclaimer in the documentation and/or other materials provided with the distribution.
  Neither the name of the Eclipse Foundation, Inc. nor the names of its contributors may be used to endorse or promote
  products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
COPYLEFT = re.compile(r"\bL?GPL|MPL|OFL")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def lic_files(d):
    """License/notice files in a dist-info folder, licenses first, in a fixed order."""
    files = [p for p in d.rglob("*") if p.is_file() and re.match(r"(?i)(licen[cs]e|copying|notice)", p.name)]
    return sorted(files, key=lambda p: (p.name.upper().startswith("NOTICE"), p.relative_to(d).as_posix()))


def item(name, version, license, url, text=None, **kw):
    d = {"name": name, "version": version, "license": license, "url": url}
    if COPYLEFT.search(license):
        d["copyleft"] = True
    if text:
        d["text"] = text
    d.update(kw)
    return d


def venv_paths(venv):
    """(site-packages, stdlib) of a virtualenv, asked from its own interpreter."""
    exe = venv / ("Scripts/python.exe" if (venv / "Scripts").is_dir() else "bin/python")
    code = "import sysconfig; print(sysconfig.get_path('purelib')); print(sysconfig.get_path('stdlib'))"
    res = subprocess.run([str(exe), "-c", code], check=True, capture_output=True, text=True)
    site, stdlib = res.stdout.split("\n")[:2]
    return Path(site), Path(stdlib)


def generate(site, python_license, libdeps, esp_core, out):
    lic_dir = out / "licenses"

    def write(name, parts):
        text = "\n\n".join(p.strip("\n") for p in parts) + "\n"
        (lic_dir / f"{slug(name)}.txt").write_text(text, encoding="utf-8")
        return f"licenses/{slug(name)}.txt"

    shutil.rmtree(lic_dir, ignore_errors=True)
    lic_dir.mkdir(parents=True)
    write("speaker-web-controller", [(REPO / "LICENSE").read_text(encoding="utf-8")])

    server = [
        item("Python", "", "PSF-2.0", "https://docs.python.org/3/license.html",
             write("python", [python_license.read_text(encoding="utf-8")])),
        item("FFmpeg", "", "LGPL-2.1-or-later / GPL", "https://ffmpeg.org/legal.html", kind="program"),
        item("Node.js", "", "MIT", "https://nodejs.org", kind="program"),
    ]
    for name, prefix, license, url in PY:
        dist = [d for d in site.glob("*.dist-info")
                if re.fullmatch(rf"{re.escape(prefix)}-[0-9].*\.dist-info", d.name, re.I)]
        if len(dist) != 1:
            raise SystemExit(f"{name}: expected one {prefix}-*.dist-info in {site}, found {len(dist)}")
        version = dist[0].name[len(prefix) + 1:-len(".dist-info")]
        files = lic_files(dist[0])
        if not files:
            raise SystemExit(f"{name}: no license file in {dist[0]}")
        parts = []
        for f in files:
            body = f.read_text(encoding="utf-8", errors="replace")
            parts.append(f"==> {f.name} <==\n\n{body}" if len(files) > 1 else body)
        if name == "paho-mqtt":  # the wheel names its two licenses but ships neither; this app uses it under the EDL
            parts.append(EDL)
        server.append(item(name, version, license, url, write(name, parts)))

    def lib_version(lib):
        return json.loads((libdeps / lib / "library.json").read_text(encoding="utf-8"))["version"]

    lgpl = write("arduino-cores-lgpl-2.1", [(esp_core / "LICENSE").read_text(encoding="utf-8")])
    firmware = [
        item("ArduinoJson", lib_version("ArduinoJson"), "MIT", "https://arduinojson.org",
             write("arduinojson", [(libdeps / "ArduinoJson/LICENSE.txt").read_text(encoding="utf-8")])),
        item("PubSubClient", lib_version("PubSubClient"), "MIT", "https://github.com/knolleary/pubsubclient",
             write("pubsubclient", [(libdeps / "PubSubClient/LICENSE.txt").read_text(encoding="utf-8")])),
        item("Arduino core for ESP32", "", "LGPL-2.1", "https://github.com/espressif/arduino-esp32", lgpl),
        item("Arduino core for ESP8266", "", "LGPL-2.1", "https://github.com/esp8266/Arduino", lgpl),
        item("Root CA certificates", "", "Public", f"{REPO_URL}/blob/main/firmware/certs/mqtt-roots.pem", kind="certs"),
    ]
    browser = [item("Anuphan", "", "OFL-1.1", "https://github.com/cadsondemak/Anuphan", "fonts/OFL.txt",
                    copyright="Copyright 2019 The Anuphan Project Authors", kind="font")]
    data = {"app": {"name": "Speaker Web Controller", "license": "MIT", "text": "licenses/speaker-web-controller.txt"},
            "groups": [{"id": "browser", "items": browser}, {"id": "server", "items": server},
                       {"id": "firmware", "items": firmware}]}
    (out / "licenses.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    files = sorted(lic_dir.iterdir())
    print(f"{len(files)} license files, {sum(p.stat().st_size for p in files)} bytes, in {lic_dir}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venv", type=Path, default=REPO / ".venv", help="virtualenv with requirements.txt installed")
    ap.add_argument("--site-packages", type=Path, help="site-packages to read instead of the venv's")
    ap.add_argument("--python-license", type=Path, help="Python's LICENSE.txt (default: the venv's stdlib copy)")
    ap.add_argument("--libdeps", type=Path, default=REPO / "firmware/.pio/libdeps/esp32dev",
                    help="the firmware's PlatformIO libdeps folder")
    ap.add_argument("--esp-core", type=Path,
                    default=Path.home() / ".platformio/packages/framework-arduinoespressif8266",
                    help="a PlatformIO Arduino core package holding the LGPL-2.1 LICENSE")
    ap.add_argument("--out", type=Path, default=REPO / "static", help="where licenses.json and licenses/ go")
    args = ap.parse_args()
    site, python_license = args.site_packages, args.python_license
    if site is None or python_license is None:
        venv_site, stdlib = venv_paths(args.venv)
        site = site or venv_site
        python_license = python_license or stdlib / "LICENSE.txt"
    generate(site, python_license, args.libdeps, args.esp_core, args.out)


if __name__ == "__main__":
    main()
