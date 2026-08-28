from __future__ import annotations

import re
from pathlib import Path

from .io import atomic_write, load_yaml
from .models import PackManifest
from .rules import RuleEngine

_SLOT = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_RULES_START = "<!-- STYLEOS:NEGATIVE_RULES:START -->"
_RULES_END = "<!-- STYLEOS:NEGATIVE_RULES:END -->"


class PackRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def discover(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(path.parent for path in self.root.glob("*/pack.yaml"))

    def load(self, pack: str | Path) -> PackManifest:
        candidate = Path(pack)
        path = candidate if candidate.name == "pack.yaml" else self.root / str(pack) / "pack.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Pack manifest not found: {pack}")
        return PackManifest.model_validate(load_yaml(path))

    def _prompt_path(self, pack: str | Path) -> Path:
        candidate = Path(pack)
        pack_name = candidate.parent.name if candidate.name == "pack.yaml" else str(pack)
        manifest = self.load(pack)
        prompt_target = manifest.targets.get("prompt")
        if not prompt_target or not prompt_target.file:
            raise ValueError(f"Pack {pack_name} has no prompt target")
        return self.root / pack_name / prompt_target.file

    def _rule_engine(self) -> RuleEngine:
        path = self.root / "global" / "deai.negative.zh.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Negative rule source not found: {path}")
        engine = RuleEngine.from_file(path)
        engine.assert_projection_parity()
        return engine

    def compile_prompt(self, pack: str | Path) -> str:
        prompt_path = self._prompt_path(pack)
        prompt = prompt_path.read_text(encoding="utf-8")
        has_start = _RULES_START in prompt
        has_end = _RULES_END in prompt
        if has_start != has_end:
            raise ValueError(f"Prompt rule markers are incomplete: {prompt_path}")
        if not has_start:
            if self.load(pack).pack == "global.deai":
                raise ValueError(f"Global de-AI prompt is missing rule projection markers: {prompt_path}")
            return prompt
        if prompt.count(_RULES_START) != 1 or prompt.count(_RULES_END) != 1:
            raise ValueError(f"Prompt rule markers must appear exactly once: {prompt_path}")
        before, remainder = prompt.split(_RULES_START, 1)
        _, after = remainder.split(_RULES_END, 1)
        projected = self._rule_engine().project_prompt()
        return f"{before}{_RULES_START}\n{projected}\n{_RULES_END}{after}"

    def prompt_drift(self, pack: str | Path) -> bool:
        prompt_path = self._prompt_path(pack)
        return prompt_path.read_text(encoding="utf-8") != self.compile_prompt(pack)

    def build_prompt(self, pack: str | Path, *, check: bool = False) -> Path:
        prompt_path = self._prompt_path(pack)
        compiled = self.compile_prompt(pack)
        if check:
            if prompt_path.read_text(encoding="utf-8") != compiled:
                raise ValueError(f"Prompt target drift detected: {prompt_path}")
            return prompt_path
        atomic_write(prompt_path, compiled)
        return prompt_path

    def build_all_prompts(self, *, check: bool = False) -> list[Path]:
        return [self.build_prompt(pack_dir.name, check=check) for pack_dir in self.discover()]

    def lint(self, pack: str | Path) -> list[str]:
        candidate = Path(pack)
        pack_dir = candidate.parent if candidate.name == "pack.yaml" else self.root / str(pack)
        errors: list[str] = []
        try:
            manifest = self.load(pack)
        except Exception as exc:
            return [str(exc)]
        prompt_target = manifest.targets.get("prompt")
        prompt_file = pack_dir / prompt_target.file if prompt_target and prompt_target.file else None
        if manifest.delivery.prompt.value == "ready":
            if prompt_file is None or not prompt_file.exists():
                errors.append("delivery.prompt=ready but prompt target is missing")
            else:
                prompt_text = prompt_file.read_text(encoding="utf-8")
                declared = {item.slot for item in manifest.inputs}
                referenced = {match.strip() for match in _SLOT.findall(prompt_text)}
                if referenced and not any(slot in reference for slot in declared for reference in referenced):
                    errors.append("prompt declares slots but none correspond to manifest inputs")
                try:
                    if self.prompt_drift(pack):
                        errors.append("prompt target has drifted from the negative-rule source")
                except (FileNotFoundError, ValueError) as exc:
                    errors.append(str(exc))
        examples = pack_dir / "examples"
        if manifest.validation.example.value == "passed" and not any(examples.glob("*")):
            errors.append("validation.example=passed but examples/ is empty")
        if manifest.validation.formal_blind_test.value == "passed" and not manifest.eval.formal_set:
            errors.append("formal_blind_test=passed requires eval.formal_set")
        if manifest.maturity.value == "production_validated":
            errors.append("production_validated must be set only by an evidence-bearing release process")
        return errors

    def lint_all(self) -> dict[str, list[str]]:
        return {pack_dir.name: self.lint(pack_dir.name) for pack_dir in self.discover()}

    def build_skill(self, pack: str, output_root: str | Path) -> Path:
        manifest = self.load(pack)
        prompt_target = manifest.targets.get("prompt")
        if not prompt_target or not prompt_target.file:
            raise ValueError(f"Pack {pack} has no prompt target")
        prompt = self.compile_prompt(pack)
        skill_dir = Path(output_root) / pack
        skill_path = skill_dir / "SKILL.md"
        inputs = "\n".join(
            f"- `{item.slot}` ({item.type}, {'required' if item.required else 'optional'}): {item.description}"
            for item in manifest.inputs
        )
        outputs = "\n".join(
            f"- `{item.name}` ({item.format}): {item.description}" for item in manifest.outputs
        )
        content = (
            f"# {manifest.name}\n\n"
            f"> Generated from `packs/{pack}/pack.yaml` and `{prompt_target.file}`. Do not edit this generated target directly.\n\n"
            f"## Inputs\n\n{inputs or '- None'}\n\n"
            f"## Outputs\n\n{outputs or '- None'}\n\n"
            f"## Execution contract\n\n{prompt.strip()}\n"
        )
        atomic_write(skill_path, content)
        return skill_path

    def build_all_skills(self, output_root: str | Path) -> list[Path]:
        return [self.build_skill(pack_dir.name, output_root) for pack_dir in self.discover()]
