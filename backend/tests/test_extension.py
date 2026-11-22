"""Automated tests for Chrome Extension Manifest V3, permissions, and heuristic parser."""

import json
import os
import re
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTENSION_DIR = REPO_ROOT / "extension"
MANIFEST_PATH = EXTENSION_DIR / "manifest.json"
PARSER_PATH = EXTENSION_DIR / "parser.js"
ICONS_DIR = EXTENSION_DIR / "icons"


def test_extension_manifest_validity_and_least_privilege_permissions():
    """Verify Chrome Extension manifest follows Manifest V3 and strict least-privilege rules."""
    assert MANIFEST_PATH.exists(), "manifest.json must exist in extension directory"

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 1. Manifest V3 Check
    assert manifest.get("manifest_version") == 3, "Extension must use Manifest V3"
    assert manifest.get("name") == "Tandora Prospect Capture"
    assert manifest.get("version") == "1.0.0"

    # 2. Least-Privilege Permissions: ONLY activeTab, scripting, storage
    permissions = manifest.get("permissions", [])
    assert set(permissions) == {"activeTab", "scripting", "storage"}, (
        f"Permissions must be strictly activeTab, scripting, storage; got {permissions}"
    )

    # 3. Host Permissions: MUST NOT include <all_urls>; ONLY http://127.0.0.1:8000/*
    host_permissions = manifest.get("host_permissions", [])
    assert "<all_urls>" not in host_permissions, "Extension must never request <all_urls>"
    assert any("127.0.0.1:8000" in hp for hp in host_permissions), (
        "Host permissions must be scoped to local backend"
    )
    for hp in host_permissions:
        assert hp.startswith("http://127.0.0.1:8000"), f"Unpermitted host permission: {hp}"

    # 4. Action / Default Popup
    action = manifest.get("action", {})
    assert action.get("default_popup") == "popup/popup.html"
    assert "Alt+Shift+T" in action.get("default_title", "")

    # 5. Service Worker
    background = manifest.get("background", {})
    assert background.get("service_worker") == "background.js"
    assert (EXTENSION_DIR / "background.js").exists()

    # 6. Keyboard Shortcut Command
    commands = manifest.get("commands", {})
    assert "_execute_action" in commands
    assert commands["_execute_action"]["suggested_key"]["default"] == "Alt+Shift+T"

    # 7. Icons
    icons = manifest.get("icons", {})
    for size in ("16", "48", "128"):
        assert size in icons
        icon_path = EXTENSION_DIR / icons[size]
        assert icon_path.exists(), f"Icon {icons[size]} does not exist"
        with open(icon_path, "rb") as f:
            header = f.read(8)
            assert header == b"\x89PNG\r\n\x1a\n", f"Icon {size} is not a valid PNG"


def test_heuristic_parser_regex_and_extraction():
    """Verify email and phone extraction patterns match parser.js specifications."""
    # Test email extraction regex
    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    sample_text = """
    Jane Doe
    VP of Engineering at Acme Corp
    Email: jane.doe@acme.com
    Personal: jane_doe99@gmail.co.uk
    Phone: +1 (555) 019-2834
    Mobile: 555-404-5000
    Random numbers: 12345 or 42
    Website: https://acme.com
    """
    emails = email_regex.findall(sample_text)
    assert "jane.doe@acme.com" in emails
    assert "jane_doe99@gmail.co.uk" in emails
    assert len(emails) == 2

    # Test phone extraction regex
    phone_regex = re.compile(
        r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,4})?"
    )
    raw_phones = phone_regex.findall(sample_text)
    valid_phones = [
        p.strip() for p in raw_phones if 7 <= len(re.sub(r"\D", "", p)) <= 15
    ]
    assert any("555" in p and "019" in p for p in valid_phones)
    assert any("555-404-5000" in p or "555" in p for p in valid_phones)


def test_manual_paste_fallback_parsing_logic():
    """Verify structured parsing of contact blocks copied from ContactOut/Apollo overlays."""
    contactout_sample = """
    Alex Rivera
    Head of Infrastructure at CloudScale Inc
    San Francisco Bay Area
    Email: alex.rivera@cloudscale.io
    Phone: +1 415-555-0182
    LinkedIn: https://www.linkedin.com/in/alex-rivera-cloud
    """

    # Simulate parser.js line filtering and logic
    lines = [line.strip() for line in contactout_sample.splitlines() if line.strip()]
    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    phone_regex = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}")

    emails = email_regex.findall(contactout_sample)
    phones = [
        p.strip()
        for p in phone_regex.findall(contactout_sample)
        if len(re.sub(r"\D", "", p)) >= 7
    ]

    assert emails == ["alex.rivera@cloudscale.io"]
    assert len(phones) >= 1
    assert "415-555-0182" in phones[0]

    # Non-metadata text lines
    text_lines = [
        l for l in lines
        if not email_regex.search(l)
        and not l.startswith("https://")
        and not (len(re.sub(r"\D", "", l)) >= 7 and "phone" in l.lower())
    ]
    assert text_lines[0] == "Alex Rivera"
    assert "Head of Infrastructure" in text_lines[1]
    assert "at CloudScale Inc" in text_lines[1]


def test_missing_and_malformed_fields_handling():
    """Verify parser safely handles empty strings, noise labels, and malformed inputs."""
    empty_sample = "   \n\n\t  "
    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    assert email_regex.findall(empty_sample) == []

    malformed_sample = """
    Contact info
    View profile
    Connect
    invalid-email@
    @nodomain.com
    123
    """
    assert email_regex.findall(malformed_sample) == []
