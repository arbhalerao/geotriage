import hashlib
from dataclasses import dataclass
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str

    @property
    def version(self) -> str:
        return f"{self.name}@{hashlib.sha256(self.text.encode()).hexdigest()[:8]}"

    def render(self, **values) -> str:
        # $placeholders rather than {braces}, because prompts quote JSON
        return Template(self.text).substitute(values)


def load_prompt(name: str, directory: Path = PROMPTS_DIR) -> Prompt:
    return Prompt(name=name, text=(directory / f"{name}.md").read_text())
