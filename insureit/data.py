"""Loading claims, user history and evidence requirements."""
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Claim:
    user_id: str
    image_paths: list[str]
    user_claim: str
    claim_object: str
    raw: dict

    @property
    def image_ids(self) -> list[str]:
        return [Path(p).stem for p in self.image_paths]


def read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_claims(path) -> list[Claim]:
    return [
        Claim(r["user_id"], r["image_paths"].split(";"), r["user_claim"], r["claim_object"], r)
        for r in read_csv(path)
    ]


def load_history(path) -> dict[str, dict]:
    return {r["user_id"]: r for r in read_csv(path)}


def load_requirements(path) -> list[dict]:
    return read_csv(path)


def requirements_for(requirements: list[dict], claim_object: str) -> list[dict]:
    return [r for r in requirements if r["claim_object"] in (claim_object, "all")]
