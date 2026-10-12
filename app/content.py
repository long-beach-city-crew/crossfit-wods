"""Workouts read once from data/<week>/wods and data/<week>/desc."""

from dataclasses import dataclass
from pathlib import Path

import markdown

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Wod:
    id: str  # "W01/1-monday", also the URL path under /wod/
    week: str
    day: str
    rest: bool
    sections: list[str]  # the "## " headings, in order
    html: str
    desc_html: str | None

    @property
    def title(self) -> str:
        return f"{self.week} – {self.day}"


def _parse(path: Path) -> tuple[dict[str, str], str]:
    _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
    meta = dict(line.split(": ", 1) for line in front.splitlines() if line)
    return meta, body.strip()


def _load(data_dir: Path) -> list[Wod]:
    wods = []
    for wod_path in sorted(data_dir.glob("W*/wods/*.md")):
        meta, body = _parse(wod_path)
        desc_path = wod_path.parent.parent / "desc" / wod_path.name
        desc_html = markdown.markdown(_parse(desc_path)[1]) if desc_path.exists() else None
        wods.append(
            Wod(
                id=f"{meta['week']}/{wod_path.stem}",
                week=meta["week"],
                day=meta["day"],
                rest=meta.get("rest") == "true",
                sections=[line[3:] for line in body.splitlines() if line.startswith("## ")],
                html=markdown.markdown(body),
                desc_html=desc_html,
            )
        )
    return wods


WODS: list[Wod] = _load(DATA_DIR)
WODS_BY_ID: dict[str, Wod] = {w.id: w for w in WODS}
