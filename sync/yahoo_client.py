from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

import requests

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def descendants_named(node: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in node.iter() if local_name(element.tag) == name]


def children_named(node: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in list(node) if local_name(element.tag) == name]


def first_text(node: ET.Element, name: str, default: str | None = None) -> str | None:
    for element in node.iter():
        if local_name(element.tag) == name:
            if element.text is None:
                return default
            value = element.text.strip()
            return value if value else default
    return default


class YahooFantasyClient:
    def __init__(self, access_token: str, session: requests.Session | Any | None = None):
        self.access_token = access_token
        self.session = session or requests.Session()

    def get_xml(self, path: str, params: dict[str, str] | None = None) -> ET.Element:
        url = f"{BASE_URL}/{path.lstrip('/')}"
        response = self.session.get(
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/xml",
            },
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return ET.fromstring(response.text)
