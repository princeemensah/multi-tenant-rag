"""Validation tests for the seed corpus utilities."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.scripts.manage_documents import SeedTenantSpec, _normalize_created_at, load_seed_dataset


def test_normalize_created_at_handles_date_and_z_suffix():
    direct = _normalize_created_at("2024-05-12")
    with_z = _normalize_created_at("2024-05-12T15:30:00Z")

    assert direct == "2024-05-12T00:00:00"
    assert with_z == "2024-05-12T15:30:00+00:00"


def test_load_seed_dataset_populates_defaults(tmp_path: Path):
    dataset = {
        "tenants": [
            {
                "name": "Example Tenant",
                "subdomain": "example",
                "documents": [
                    {
                        "title": "Example Doc",
                        "filename": "example_doc.txt",
                        "document_type": "policy",
                        "created_at": "2024-04-01",
                        "tags": ["compliance", "policy"],
                        "metadata": {"owner": "GRC"},
                        "content": "Guidance for the assistant."
                    }
                ]
            }
        ]
    }

    dataset_path = tmp_path / "seed.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

    tenants = load_seed_dataset(dataset_path)

    assert isinstance(tenants[0], SeedTenantSpec)
    doc_spec = tenants[0].documents[0]

    assert doc_spec.metadata["document_type"] == "policy"
    assert doc_spec.metadata["source_system"] == "seed_corpus"
    assert doc_spec.created_at == "2024-04-01T00:00:00"
    assert doc_spec.tags.count("policy") == 1
    assert set(doc_spec.tags) == {"compliance", "policy"}

    parsed = datetime.fromisoformat(doc_spec.created_at)
    assert parsed.year == 2024 and parsed.month == 4 and parsed.day == 1


def test_load_seed_dataset_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_seed_dataset(missing)
