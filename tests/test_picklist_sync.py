import io
import json
import zipfile

import httpx

from tm_advisor.ipa_auth import IpaToken
from tm_advisor.picklist import Picklist
from tm_advisor.picklist_sync import fetch, parse, save

CSV = (
    "﻿Description ID,Class Number,Description,Status\n"
    "101,25,Clothing,Active\n"
    "102,25,  Knitted   garments ,Active\n"
    "103,25,Clothing,Active\n"          # duplicate
    "104,25,Retired thing,Inactive\n"   # inactive
    "105,99,Bad class,Active\n"         # not a Nice class
    "106,35,Retail services in relation to clothing,Active\n"
)


def test_parse_csv_cleans_and_filters():
    items = parse(CSV.encode("utf-8"))
    assert items == [
        {"id": "101", "class_number": 25, "description": "Clothing"},
        {"id": "102", "class_number": 25, "description": "Knitted garments"},
        {"id": "106", "class_number": 35, "description": "Retail services in relation to clothing"},
    ]


def test_parse_json_and_zip():
    as_json = json.dumps({"goodsAndServicesDescriptions": [{"id": 7, "classNumber": "9", "descriptionText": "Smartwatches"}]})
    assert parse(as_json.encode()) == [{"id": "7", "class_number": 9, "description": "Smartwatches"}]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("picklist.csv", CSV)
    assert len(parse(buffer.getvalue())) == 3


def test_saved_file_loads_as_picklist(tmp_path):
    save(parse(CSV.encode()), tmp_path / "picklist.json")
    assert Picklist.load(tmp_path / "picklist.json").match(25, "knitted garment").id == "102"


def test_fetch_uses_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 60})
        assert request.url.path == "/v1/gsDescriptionsFull"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, content=CSV.encode())

    http = httpx.Client(transport=httpx.MockTransport(handler))
    content = fetch(IpaToken("id", "secret", "https://auth.example/token", http), http, "https://api.example/v1")
    assert len(parse(content)) == 3
