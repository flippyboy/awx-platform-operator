#!/usr/bin/env python3
"""Fail if AWX / AWXGateway / AWXPlatform documents have wrong JSON/YAML types.

Catches the v0.1.7–v0.1.8 class of bugs:
  - playbook YAML parsed before Jinja (unquoted default([]|true))
  - quoted Jinja that stringifies CRD booleans → API 422

Usage:
  python3 hack/scripts/check-cr-types.py
  python3 hack/scripts/check-cr-types.py --helm /tmp/helm-render.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
CRD_DIR = ROOT / "config" / "crd" / "bases"
TEMPLATES = ROOT / "roles" / "platform" / "templates"
PLATFORM_TASKS = ROOT / "roles" / "platform" / "tasks" / "main.yml"

KINDS = {
    "AWX": "awx.ansible.com_awxs.yaml",
    "AWXGateway": "awx.ansible.com_awxgateways.yaml",
    "AWXPlatform": "awx.ansible.com_awxplatforms.yaml",
}

BOOL_TRUTHY = {"true", "yes", "on", "1"}
BOOL_FALSY = {"false", "no", "off", "0", ""}


def ansible_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    text = str(value).strip().lower()
    if text in BOOL_TRUTHY:
        return True
    if text in BOOL_FALSY:
        return False
    return bool(value)


def ansible_ternary(value, true_val, false_val):
    return true_val if ansible_bool(value) else false_val


def to_nice_yaml(value, **_kwargs) -> str:
    return yaml.safe_dump(value, default_flow_style=False).rstrip()


def collect_typed_fields(schema: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for name, spec in (schema.get("properties") or {}).items():
        path = f"{prefix}.{name}" if prefix else name
        typ = spec.get("type")
        if typ in {"boolean", "integer", "string", "array", "object"}:
            out[path] = typ
        if isinstance(spec, dict) and "properties" in spec:
            out.update(collect_typed_fields(spec, path))
    return out


def load_crd_types() -> dict[str, dict[str, str]]:
    types: dict[str, dict[str, str]] = {}
    for kind, filename in KINDS.items():
        doc = yaml.safe_load((CRD_DIR / filename).read_text())
        versions = doc["spec"]["versions"]
        schema = versions[0]["schema"]["openAPIV3Schema"]
        spec_schema = (schema.get("properties") or {}).get("spec") or {}
        types[kind] = collect_typed_fields(spec_schema)
    return types


def walk_check(obj, expected: dict[str, str], prefix: str, errors: list[str]) -> None:
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        want = expected.get(path)
        if want == "boolean" and not isinstance(value, bool):
            errors.append(f"{path}: want boolean, got {type(value).__name__}={value!r}")
        elif want == "integer" and not isinstance(value, int):
            errors.append(f"{path}: want integer, got {type(value).__name__}={value!r}")
        elif want == "string" and value is not None and not isinstance(value, str):
            errors.append(f"{path}: want string, got {type(value).__name__}={value!r}")
        elif want == "array" and value is not None and not isinstance(value, list):
            errors.append(f"{path}: want array, got {type(value).__name__}={value!r}")
        if isinstance(value, dict):
            walk_check(value, expected, path, errors)


def render_platform_templates() -> list[dict]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    env.filters["bool"] = ansible_bool
    env.filters["ternary"] = ansible_ternary
    env.filters["to_nice_yaml"] = to_nice_yaml

    ctx = {
        "__gateway_name": "awx-gateway",
        "__controller_name": "awx-controller",
        "__admin_password_secret": "awx-admin-password",
        "__postgres_secret": "awx-postgres-configuration",
        "__redis_secret": "",
        "__ingress_type": "ingress",
        "__gateway_service_secret": "awx-gateway-controller-service-secret",
        "ansible_operator_meta": {"name": "awx", "namespace": "awx"},
        "admin_user": "admin",
        "open_source_defaults": "true",  # ansible-operator often stringifies
        "gateway_validate_certs": "false",
        "controller": {
            "image": "ghcr.io/ansible/awx",
            "image_version": "devel",
        },
        "gateway": {
            "image": "ghcr.io/flippyboy/awx/jewel-with-ui",
            "image_version": "0.1.0",
            "ui_mode": "baked",
            "ui_image": "",
            "envoy_enabled": "true",
            "tls_secret": "",
            "create_certificate": "true",
            "create_tls_issuer": "true",
            "tls_issuer": "",
            "tls_issuer_kind": "Issuer",
            "tls_dns_names": ["awx.example.com"],
            "controller_service_port": "80",
            "controller_service_https": "false",
        },
        "ingress": {
            "ingress_class_name": "cilium",
            "hosts": [{"hostname": "awx.example.com"}],
            "tls_secret": "awx-edge-tls",
        },
    }
    docs = []
    for name in ("awxgateway.yaml.j2", "awx.yaml.j2"):
        rendered = env.get_template(name).render(**ctx)
        doc = yaml.safe_load(rendered)
        if not isinstance(doc, dict):
            raise SystemExit(f"{name} did not render to a mapping:\n{rendered}")
        docs.append(doc)
    return docs


def check_docs(docs: list[dict], types: dict[str, dict[str, str]], origin: str) -> list[str]:
    errors: list[str] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        if kind not in types:
            continue
        spec = doc.get("spec") or {}
        found: list[str] = []
        walk_check(spec, types[kind], "", found)
        errors.extend(f"{origin} {kind}/{doc.get('metadata', {}).get('name', '?')}: {e}" for e in found)
        meta = doc.get("metadata") or {}
        if not meta.get("name"):
            errors.append(f"{origin} {kind}: metadata.name missing")
        if not meta.get("namespace") and origin.startswith("template"):
            errors.append(f"{origin} {kind}: metadata.namespace missing")
    return errors


def check_platform_role_pattern() -> list[str]:
    text = PLATFORM_TASKS.read_text()
    errors = []
    if "lookup('template', 'awxgateway.yaml.j2') | from_yaml" not in text:
        errors.append("platform tasks must apply AWXGateway via lookup|from_yaml")
    if "lookup('template', 'awx.yaml.j2') | from_yaml" not in text:
        errors.append("platform tasks must apply AWX via lookup|from_yaml")
    # Inline quoted Jinja for known boolean CR fields (the v0.1.8 bug)
    for field in (
        "create_certificate",
        "create_tls_issuer",
        "create_tls_ca_configmap",
        "envoy_enabled",
        "controller_service_https",
        "open_source_defaults",
        "gateway_validate_certs",
    ):
        needle = f'{field}: "{{{{'
        if needle in text:
            errors.append(
                f"platform tasks inline-quote {field}; that becomes a string (use j2 + from_yaml)"
            )
    if "metadata:" not in text or "namespace: '{{ ansible_operator_meta.namespace }}'" not in text:
        errors.append("Label AWXPlatform must set metadata.namespace (not top-level namespace)")
    return errors


def parse_multi(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--helm", type=Path, help="helm template output to type-check")
    args = parser.parse_args()

    types = load_crd_types()
    errors = check_platform_role_pattern()
    errors.extend(check_docs(render_platform_templates(), types, "template"))

    if args.helm:
        errors.extend(check_docs(parse_multi(args.helm), types, f"helm:{args.helm}"))

    if errors:
        print("CR type check failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("CR type check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
