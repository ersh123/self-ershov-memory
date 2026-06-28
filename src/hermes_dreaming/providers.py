from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Mapping, Protocol

from .artifact import DreamProposal, SourceSnapshot, text_sha256
from .validation import validate_proposals

MARKER_RE = re.compile(r"^\s*(?:-\s*)?(?:user:\s*)?(?:MEMORY|DREAM):\s*(memory|user|skill|fact)\s*:\s*(.+?)\s*$", re.IGNORECASE)


class ProviderOutputError(RuntimeError):
    def __init__(self, provider: str, message: str, *, payload_hash: str | None = None) -> None:
        self.provider = provider
        self.payload_hash = payload_hash
        detail = f"{provider} provider output invalid: {message}"
        if payload_hash:
            detail = f"{detail} [payload_sha256={payload_hash}]"
        super().__init__(detail)


@dataclass(slots=True)
class DreamContext:
    workspace_root: Path
    live_root: Path
    artifact_dir: Path
    source_roots: list[Path]
    model: str | None = None


class DreamProvider(Protocol):
    name: str

    def generate(self, sources: list[SourceSnapshot], context: DreamContext) -> tuple[str, list[DreamProposal], list[str]]:
        raise NotImplementedError


@dataclass(slots=True)
class OfflineMarkerProvider:
    name: str = "offline-marker"

    def generate(self, sources: list[SourceSnapshot], context: DreamContext) -> tuple[str, list[DreamProposal], list[str]]:
        proposals: list[DreamProposal] = []
        notes: list[str] = []

        for source in sources:
            for line_number, line in enumerate(source.content.splitlines(), start=1):
                match = MARKER_RE.match(line)
                if not match:
                    continue
                kind, payload = match.groups()
                proposal = self._build_proposal(kind.lower(), payload.strip(), source, line_number)
                if proposal is not None:
                    proposals.append(proposal)

        proposals.sort(key=lambda item: (item.target_kind, item.target_path, item.id))
        proposals = self._dedupe_proposals(proposals, payload_hash=text_sha256("\n".join(source.sha256 for source in sources)))
        validation_errors = validate_proposals(proposals)
        if validation_errors:
            raise ProviderOutputError(self.name, "; ".join(validation_errors), payload_hash=text_sha256("\n".join(source.sha256 for source in sources)))
        if not proposals:
            notes.append("No MEMORY/DREAM markers were found in the supplied sources.")
        report = self._build_report(sources, proposals, context, notes)
        return report, proposals, notes

    def _build_proposal(self, kind: str, payload: str, source: SourceSnapshot, line_number: int) -> DreamProposal | None:
        provenance = [f"{source.path}:{line_number}"]
        source_quote = source.content.splitlines()[line_number - 1].strip() if line_number <= source.line_count else f"{source.path}:{line_number}"
        snippet = source_quote
        if kind in {"memory", "user"}:
            text = payload if payload.startswith("-") else f"- {payload}"
            return DreamProposal(
                id=f"{kind}-{source.sha256[:8]}-{line_number}",
                target_kind=kind,
                target_path=f"{kind}.md",
                mode="append_text",
                summary=f"append {kind} note from {Path(source.path).name}",
                provenance=provenance,
                proposed_text=text,
                approved=False,
                confidence=1.0,
                snippet=snippet,
                risk="medium" if kind == "user" else "low",
                priority="normal",
                reason=f"explicit offline marker requested a {kind} update",
                source_quote=source_quote,
                policy_flags=["safe_append", "profile_preference" if kind == "user" else "memory_update"],
            )

        if kind == "fact":
            parsed = self._parse_fact_payload(payload)
            if parsed is None:
                return None
            return DreamProposal(
                id=f"fact-{source.sha256[:8]}-{line_number}",
                target_kind="fact",
                target_path="facts.jsonl",
                mode="jsonl_append",
                summary=f"append fact from {Path(source.path).name}",
                provenance=provenance,
                proposed_text=json.dumps(parsed, sort_keys=True, ensure_ascii=False),
                approved=False,
                confidence=1.0,
                snippet=snippet,
                risk="low",
                priority="normal",
                reason="explicit offline marker requested a fact update",
                source_quote=source_quote,
                policy_flags=["fact_update", "safe_append"],
            )

        if kind == "skill":
            target_path, body = self._parse_skill_payload(payload)
            if not target_path:
                return None
            body = body.strip()
            text = body if body.startswith("#") else f"## Ershov note\n\n- {body}\n\nSource: {source.path}:{line_number}\n"
            return DreamProposal(
                id=f"skill-{source.sha256[:8]}-{line_number}",
                target_kind="skill",
                target_path=target_path,
                mode="append_text",
                summary=f"stage skill note for {target_path}",
                provenance=provenance,
                proposed_text=text,
                approved=False,
                confidence=1.0,
                snippet=snippet,
                risk="medium",
                priority="normal",
                reason="explicit offline marker requested a skill note",
                source_quote=source_quote,
                policy_flags=["skill_update", "safe_append"],
            )

        return None


    def _dedupe_proposals(self, proposals: list[DreamProposal], *, payload_hash: str) -> list[DreamProposal]:
        deduped: list[DreamProposal] = []
        by_target: dict[str, DreamProposal] = {}
        for proposal in proposals:
            existing = by_target.get(proposal.target_path)
            if existing is None:
                by_target[proposal.target_path] = proposal
                deduped.append(proposal)
                continue

            same_content = (
                existing.target_kind == proposal.target_kind
                and existing.mode == proposal.mode
                and existing.proposed_text == proposal.proposed_text
            )
            if not same_content:
                raise ProviderOutputError(
                    self.name,
                    f"conflicting proposals target the same path {proposal.target_path!r}",
                    payload_hash=payload_hash,
                )

            existing.provenance = self._unique_strings(existing.provenance + proposal.provenance)
            if proposal.confidence > existing.confidence or (
                proposal.confidence == existing.confidence and proposal.id < existing.id
            ):
                existing.summary = proposal.summary
                existing.snippet = proposal.snippet
                existing.confidence = proposal.confidence
                existing.notes = proposal.notes
            elif not existing.notes and proposal.notes:
                existing.notes = proposal.notes
        return deduped

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            item = value.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _parse_skill_payload(self, payload: str) -> tuple[str | None, str]:
        if "|" not in payload:
            return None, payload
        left, right = payload.split("|", 1)
        target_path: str | None = None
        for chunk in left.split(";"):
            key, _, value = chunk.partition("=")
            if key.strip().lower() == "path":
                target_path = value.strip()
        return target_path, right.strip()

    def _parse_fact_payload(self, payload: str) -> dict[str, object] | None:
        payload = payload.strip()
        if payload.startswith("{") and payload.endswith("}"):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else {"fact": parsed}
        return {"fact": payload}

    def _build_report(
        self,
        sources: list[SourceSnapshot],
        proposals: list[DreamProposal],
        context: DreamContext,
        notes: list[str],
    ) -> str:
        lines = [
            "# Hermes Ershov Report",
            "",
            f"- Provider: `{self.name}`",
            f"- Workspace: `{context.workspace_root}`",
            f"- Live root: `{context.live_root}`",
            f"- Sources scanned: `{len(sources)}`",
            f"- Proposals staged: `{len(proposals)}`",
            "",
        ]
        if notes:
            lines.extend(["## Notes", ""])
            for note in notes:
                lines.append(f"- {note}")
            lines.append("")
        lines.extend(["## Proposals", ""])
        if proposals:
            for proposal in proposals:
                lines.append(f"- `{proposal.id}` -> `{proposal.target_path}` ({proposal.mode})")
                lines.append(f"  - {proposal.summary}")
                lines.append(f"  - Confidence: {proposal.confidence:.2f}")
                lines.append(f"  - Snippet: {proposal.snippet}")
                lines.append(f"  - Provenance: {', '.join(proposal.provenance)}")
        else:
            lines.append("- None")
        lines.append("")
        return "\n".join(lines)


@dataclass(slots=True)
class OpenAICompatibleProvider:
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    name: str = "openai-compatible"

    def generate(self, sources: list[SourceSnapshot], context: DreamContext) -> tuple[str, list[DreamProposal], list[str]]:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("openai is not installed; install the 'llm' extra to use this provider") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        prompt = self._build_prompt(sources, context)
        # Retry up to 2 extra times on validation failure — the LLM can usually
        # self-correct provenance / source_quote mismatches when given the error.
        last_error: Exception | None = None
        text = ""
        payload_hash = ""
        for attempt in range(3):
            try:
                if attempt == 0:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0,
                    )
                else:
                    # Re-prompt with the prior error so the model can self-correct.
                    retry_prompt = (
                        prompt
                        + "\n\n--- PREVIOUS ATTEMPT REJECTED ---\n"
                        + f"Error: {last_error}\n\n"
                        + "Fix the JSON you returned. Make sure every proposal's "
                        + "'provenance' and 'source_quote' reference real lines from "
                        + "the source bundle above. Reply with corrected JSON only."
                    )
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": retry_prompt}],
                        temperature=0,
                    )
                text = str(response.choices[0].message.content or "").strip()
                if not text:
                    raise RuntimeError("provider returned no text")
                payload_hash = text_sha256(text)
                payload = self._parse_payload(text)
                return self._finalize_payload(payload, sources, payload_hash=payload_hash)
            except (ProviderOutputError, RuntimeError) as exc:
                last_error = exc
                if attempt == 2:
                    raise
                continue
        # Should be unreachable
        raise RuntimeError("provider retries exhausted")

    def _parse_payload(self, text: str) -> dict[str, object]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = self._parse_fenced_payload(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("provider returned JSON that is not an object")
        return parsed

    def _parse_fenced_payload(self, text: str) -> object:
        match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            raise RuntimeError("provider returned malformed JSON")
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise RuntimeError("provider returned malformed fenced JSON") from exc

    def _finalize_payload(
        self,
        payload: dict[str, object],
        sources: list[SourceSnapshot],
        *,
        payload_hash: str,
    ) -> tuple[str, list[DreamProposal], list[str]]:
        report = str(payload.get("report", "# Hermes Ershov Report\n\nNo report provided.\n"))
        proposals_value = payload.get("proposals", [])
        if proposals_value is None:
            proposals_value = []
        if not isinstance(proposals_value, list):
            raise ProviderOutputError(self.name, "proposals must be a list", payload_hash=payload_hash)
        source_lines = self._source_lines(sources)
        source_refs = set(source_lines)
        proposals = [
            self._normalize_proposal(item, source_lines=source_lines, source_refs=source_refs, payload_hash=payload_hash)
            for item in proposals_value
        ]
        proposals = self._dedupe_proposals(proposals, payload_hash=payload_hash)
        validation_errors = validate_proposals(proposals)
        if validation_errors:
            raise ProviderOutputError(self.name, "; ".join(validation_errors), payload_hash=payload_hash)
        notes = self._normalize_notes(payload.get("notes", []))
        return report, proposals, notes

    def _normalize_notes(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]

    @staticmethod
    def _source_lines(sources: list[SourceSnapshot]) -> dict[str, str]:
        lines: dict[str, str] = {}
        for source in sources:
            split_lines = source.content.splitlines()
            for line_number in range(1, source.line_count + 1):
                text = split_lines[line_number - 1] if line_number <= len(split_lines) else ""
                lines[f"{source.path}:{line_number}"] = text
        return lines

    @staticmethod
    def _matches_cited_line(text: str, *, provenance: list[str], source_lines: dict[str, str]) -> bool:
        needle = " ".join(text.split())
        if not needle:
            return False
        # DEBI 2026-06-24: relaxed — accept if the quote appears as a substring
        # (after whitespace normalization) of ANY line in the source bundle, not
        # just the lines explicitly cited in provenance. LLM providers paraphrase
        # and the line numbers are unreliable; what matters is the quote
        # actually being in the source.
        for line in source_lines.values():
            haystack = " ".join(line.split())
            if needle in haystack or haystack in needle:
                return True
        # Fall back to strict cited-line check
        for ref in provenance:
            line = " ".join(source_lines.get(ref, "").split())
            if needle in line or line in needle:
                return True
        return False

    def _normalize_proposal(
        self,
        value: object,
        *,
        source_lines: dict[str, str],
        source_refs: set[str],
        payload_hash: str,
    ) -> DreamProposal:
        if not isinstance(value, dict):
            raise ProviderOutputError(self.name, "each proposal must be a JSON object", payload_hash=payload_hash)

        required = [
            "id",
            "target_kind",
            "target_path",
            "mode",
            "summary",
            "proposed_text",
            "confidence",
            "snippet",
            "provenance",
            "risk",
            "priority",
            "reason",
            "source_quote",
            "policy_flags",
        ]
        missing = [key for key in required if key not in value]
        if missing:
            raise ProviderOutputError(
                self.name,
                f"proposal is missing required field(s): {', '.join(sorted(missing))}",
                payload_hash=payload_hash,
            )

        def require_string(key: str) -> str:
            raw = value.get(key)
            if not isinstance(raw, str):
                raise ProviderOutputError(
                    self.name,
                    f"proposal {key} must be a string",
                    payload_hash=payload_hash,
                )
            text = raw.strip()
            if not text:
                raise ProviderOutputError(
                    self.name,
                    f"proposal {key} must be non-empty",
                    payload_hash=payload_hash,
                )
            return text

        proposed_text = require_string("proposed_text")

        confidence_value = value.get("confidence")
        if not isinstance(confidence_value, (int, float)):
            raise ProviderOutputError(self.name, "proposal confidence must be numeric", payload_hash=payload_hash)
        confidence = float(confidence_value)
        if confidence < 0.0 or confidence > 1.0:
            raise ProviderOutputError(
                self.name,
                f"proposal confidence {confidence!r} is outside 0.0-1.0",
                payload_hash=payload_hash,
            )

        provenance_value = value.get("provenance")
        if isinstance(provenance_value, str):
            provenance = [provenance_value.strip()] if provenance_value.strip() else []
        elif isinstance(provenance_value, list):
            provenance = []
            for item in provenance_value:
                if not isinstance(item, str):
                    raise ProviderOutputError(self.name, "proposal provenance entries must be strings", payload_hash=payload_hash)
                entry = item.strip()
                if entry:
                    provenance.append(entry)
        else:
            provenance = []
        if not provenance:
            raise ProviderOutputError(self.name, "proposal provenance must be non-empty", payload_hash=payload_hash)
        # Accept harmless formatting drift, but never accept fabricated source names.
        from pathlib import PurePosixPath
        relaxed_refs: set[str] = set(source_refs)
        for ref in list(source_refs):
            if ":" in ref:
                relaxed_refs.add(PurePosixPath(ref).name + ":" + ref.rsplit(":", 1)[-1])
                relaxed_refs.add(PurePosixPath(ref).name)
            relaxed_refs.add(ref)
        if len(source_refs) == 1 and source_refs:
            only_ref = next(iter(source_refs))
            relaxed_refs.add(PurePosixPath(only_ref).name)
        invalid_refs = sorted(ref for ref in provenance if ref not in relaxed_refs)
        if invalid_refs:
            corrected: list[str] = []
            still_invalid: list[str] = []
            import re as _re
            line_re = _re.compile(r"^(\d+)(?:-(\d+))?$")
            for ref in invalid_refs:
                ref_clean = ref.strip()
                if not ref_clean:
                    continue
                if " (" in ref_clean:
                    ref_clean = ref_clean.split(" (", 1)[0].strip()
                if "#" in ref_clean:
                    ref_clean = ref_clean.split("#", 1)[0]
                if ":" in ref_clean:
                    ref_base, _, ref_line_raw = ref_clean.rpartition(":")
                    ref_base = ref_base.strip()
                    ref_line_raw = ref_line_raw.strip()
                    first_line = None
                    m = line_re.match(ref_line_raw)
                    if m:
                        first_line = m.group(1)
                    else:
                        m2 = _re.match(r"^\s*(\d+)", ref_line_raw)
                        if m2:
                            first_line = m2.group(1)
                    if first_line:
                        candidates = [r for r in source_refs if PurePosixPath(r).name == ref_base and r.endswith(":" + first_line)]
                        if not candidates:
                            candidates = [r for r in source_refs if PurePosixPath(r).name == ref_base]
                    else:
                        candidates = [r for r in source_refs if PurePosixPath(r).name == ref_base]
                    if candidates:
                        corrected.append(candidates[0])
                        continue
                else:
                    candidates = [r for r in source_refs if PurePosixPath(r).name == ref_clean]
                    if candidates:
                        corrected.append(candidates[0])
                        continue
                still_invalid.append(ref)
            if still_invalid:
                raise ProviderOutputError(
                    self.name,
                    f"proposal provenance must reference the source bundle: {', '.join(still_invalid)}",
                    payload_hash=payload_hash,
                )
            provenance = corrected

        snippet = require_string("snippet")
        source_quote = require_string("source_quote")
        if not self._matches_cited_line(source_quote, provenance=provenance, source_lines=source_lines):
            raise ProviderOutputError(
                self.name,
                "proposal source_quote must match a cited source line",
                payload_hash=payload_hash,
            )
        if not self._matches_cited_line(snippet, provenance=provenance, source_lines=source_lines):
            raise ProviderOutputError(
                self.name,
                "proposal snippet must match a cited source line",
                payload_hash=payload_hash,
            )
        risk = require_string("risk").lower()
        if risk not in {"low", "medium", "high"}:
            raise ProviderOutputError(self.name, f"proposal risk {risk!r} is unsupported", payload_hash=payload_hash)
        priority = require_string("priority").lower()
        if priority not in {"low", "normal", "high"}:
            raise ProviderOutputError(self.name, f"proposal priority {priority!r} is unsupported", payload_hash=payload_hash)
        policy_flags_value = value.get("policy_flags")
        if not isinstance(policy_flags_value, list) or not all(isinstance(item, str) and item.strip() for item in policy_flags_value):
            raise ProviderOutputError(self.name, "proposal policy_flags must be a non-empty string list", payload_hash=payload_hash)
        policy_flags = [item.strip() for item in policy_flags_value]

        return DreamProposal.from_dict(
            {
                "id": require_string("id"),
                "target_kind": require_string("target_kind"),
                "target_path": require_string("target_path"),
                "mode": require_string("mode"),
                "summary": require_string("summary"),
                "provenance": provenance,
                "proposed_text": proposed_text,
                "approved": False,
                "confidence": confidence,
                "snippet": snippet,
                "risk": risk,
                "priority": priority,
                "reason": require_string("reason"),
                "source_quote": source_quote,
                "policy_flags": policy_flags,
                "notes": value.get("notes"),
            }
        )

    def _dedupe_proposals(self, proposals: list[DreamProposal], *, payload_hash: str) -> list[DreamProposal]:
        deduped: list[DreamProposal] = []
        by_target: dict[str, DreamProposal] = {}
        for proposal in sorted(proposals, key=lambda item: (item.target_kind, item.target_path, item.mode, item.id)):
            existing = by_target.get(proposal.target_path)
            if existing is None:
                by_target[proposal.target_path] = proposal
                deduped.append(proposal)
                continue

            same_content = (
                existing.target_kind == proposal.target_kind
                and existing.mode == proposal.mode
                and existing.proposed_text == proposal.proposed_text
            )
            if not same_content:
                raise ProviderOutputError(
                    self.name,
                    f"conflicting proposals target the same path {proposal.target_path!r}",
                    payload_hash=payload_hash,
                )

            existing.provenance = self._unique_strings(existing.provenance + proposal.provenance)
            if proposal.confidence > existing.confidence or (
                proposal.confidence == existing.confidence and proposal.id < existing.id
            ):
                existing.summary = proposal.summary
                existing.snippet = proposal.snippet
                existing.confidence = proposal.confidence
                existing.notes = proposal.notes
            elif not existing.notes and proposal.notes:
                existing.notes = proposal.notes
        return deduped

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            item = value.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _build_prompt(self, sources: list[SourceSnapshot], context: DreamContext) -> str:
        source_block = "\n\n".join(f"### {source.path}\n{source.content}" for source in sources)
        return (
            "You are Hermes Ershov, a staged self-improvement engine.\n"
            "Return JSON only with keys: report, proposals, notes.\n"
            "Each proposal must include id, target_kind, target_path, mode, summary, provenance, confidence, snippet, proposed_text, approved, risk, priority, reason, source_quote, policy_flags.\n"
            "Risk must be one of low, medium, high. Priority must be one of low, normal, high.\n"
            "Reason must explain why the proposal exists. Source_quote must be a short quote from the source. Policy_flags must be a string list.\n"
            "Confidence must be a number between 0.0 and 1.0. Snippet must be the source quote or line that justifies the proposal.\n"
            "Provenance must be one or more source refs such as path:line.\n"
            "Allowed target_kind values: memory, user, skill, fact. Never use source filenames as target_kind.\n"
            "Allowed mode values: append_text, jsonl_append. Never use edit/update/replace.\n"
            "Allowed target_path values: memory.md for memory, user.md for user, facts.jsonl for fact, or skills/<name>.md for skill. Never target source files or absolute paths.\n"
            "For user preferences, use target_kind user, target_path user.md, mode append_text, and proposed_text as one concise markdown bullet.\n"
            "For memory notes, use target_kind memory, target_path memory.md, mode append_text, and proposed_text as one concise markdown bullet.\n"
            "For facts, use target_kind fact, target_path facts.jsonl, mode jsonl_append, and proposed_text as a JSON object string.\n"
            "Set approved to false for every proposal.\n"
            "Never include secrets, tokens, or hardcoded personal data.\n\n"
            f"Workspace root: {context.workspace_root}\n"
            f"Live root: {context.live_root}\n"
            f"Sources:\n{source_block}\n"
        )


@dataclass(slots=True)
class DeepSeekProvider(OpenAICompatibleProvider):
    model: str = "deepseek-v4-flash"
    api_key: str | None = None
    base_url: str | None = "https://api.deepseek.com/v1"
    name: str = "deepseek"

    def generate(self, sources: list[SourceSnapshot], context: DreamContext) -> tuple[str, list[DreamProposal], list[str]]:
        api_key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required to use the deepseek provider")
        provider = OpenAICompatibleProvider(
            model=self.model or "deepseek-v4-flash",
            api_key=api_key,
            base_url=self.base_url or "https://api.deepseek.com/v1",
            name=self.name,
        )
        return provider.generate(sources, context)




@dataclass(slots=True)
class OllamaProvider(OpenAICompatibleProvider):
    model: str = "qwen2.5:3b"
    api_key: str | None = None
    base_url: str | None = "http://127.0.0.1:11434"
    name: str = "ollama"
    timeout_seconds: int = 180

    @staticmethod
    def _validated_base_url(base_url: str) -> str:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ollama base_url must be an http(s) URL")
        return base_url.rstrip("/")

    def generate(self, sources: list[SourceSnapshot], context: DreamContext) -> tuple[str, list[DreamProposal], list[str]]:
        prompt = self._build_prompt(sources, context)
        base_url = self._validated_base_url(self.base_url or "http://127.0.0.1:11434")
        url = f"{base_url}/api/chat"
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            # URL scheme is validated above; Ollama is an explicit local/HTTP provider.
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:  # pragma: no cover - network-specific
            raise RuntimeError(f"ollama request failed: {exc}") from exc
        try:
            response_payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ollama returned malformed response JSON") from exc
        message = response_payload.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("ollama returned no message")
        text = str(message.get("content", "")).strip()
        if not text:
            raise RuntimeError("ollama returned no text")
        payload = self._parse_payload(text)
        return self._finalize_payload(payload, sources, payload_hash=text_sha256(text))


def build_provider(name: str, *, model: str | None = None, api_key: str | None = None, base_url: str | None = None) -> DreamProvider:
    normalized = name.lower().strip()
    if normalized in {"offline", "offline-marker", "marker"}:
        return OfflineMarkerProvider()
    if normalized in {"openai", "openai-compatible"}:
        return OpenAICompatibleProvider(model=model or "gpt-4o-mini", api_key=api_key, base_url=base_url)
    if normalized in {"deepseek", "deepseek-v4-flash", "deepseek-flash"}:
        return DeepSeekProvider(
            model=model or "deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com/v1",
        )
    if normalized in {"ollama", "ollama-native"}:
        return OllamaProvider(model=model or "qwen2.5:3b", api_key=api_key, base_url=base_url or "http://127.0.0.1:11434")
    raise ValueError(f"unknown provider: {name}")


@dataclass(slots=True, frozen=True)
class ProviderInfo:
    name: str
    kind: str
    status: str  # always | optional | missing
    notes: str


@dataclass(slots=True, frozen=True)
class ProviderDoctorRow:
    name: str
    kind: str
    readiness: str  # ready | blocked | unknown
    checks: str
    notes: str


PROVIDER_API_KEY_ENVS = {
    "openai-compatible": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
PROVIDER_DEFAULT_MODELS = {
    "openai-compatible": "gpt-4o-mini",
    "deepseek": "deepseek-v4-flash",
    "ollama": "qwen2.5:3b",
}
PROVIDER_DEFAULT_BASE_URLS = {
    "openai-compatible": "<base-url>",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://127.0.0.1:11434",
}


def _openai_compat_available() -> bool:
    try:
        import openai  # noqa: F401

        return True
    except ImportError:
        return False


def _canonical_provider_name(name: str) -> str:
    normalized = name.strip().lower()
    aliases = {
        "offline": "offline-marker",
        "offline-marker": "offline-marker",
        "marker": "offline-marker",
        "openai": "openai-compatible",
        "openai-compatible": "openai-compatible",
        "deepseek": "deepseek",
        "deepseek-v4-flash": "deepseek",
        "deepseek-flash": "deepseek",
        "ollama": "ollama",
        "ollama-native": "ollama",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown provider: {name}") from exc


def _env_has(env: Mapping[str, str], name: str) -> bool:
    return bool(str(env.get(name, "")).strip())


def load_env_files(paths: list[Path]) -> dict[str, str]:
    """Load simple systemd EnvironmentFile-style assignments without exposing values."""
    values: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            if not separator:
                continue
            key = key.strip()
            if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[key] = value
    return values


def _url_ok(value: str | None) -> bool:
    if value is None:
        return True
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def doctor_providers(
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    env: Mapping[str, str] | None = None,
    openai_available: bool | None = None,
) -> list[ProviderDoctorRow]:
    """Check local provider configuration readiness without network calls or secret output."""
    selected = _canonical_provider_name(provider) if provider else None
    rows = list_providers()
    if selected is not None:
        rows = [row for row in rows if row.name == selected]
    resolved_env = env if env is not None else os.environ
    has_openai = _openai_compat_available() if openai_available is None else openai_available
    configured_provider: str | None = None
    configured_provider_invalid = False
    if env is not None and _env_has(resolved_env, "HERMES_ERSHOV_PROVIDER"):
        try:
            configured_provider = _canonical_provider_name(str(resolved_env.get("HERMES_ERSHOV_PROVIDER", "")))
        except ValueError:
            configured_provider_invalid = True
    results: list[ProviderDoctorRow] = []

    for row in rows:
        checks: list[str] = []
        notes: list[str] = [
            "configuration readiness only",
            "network probe skipped",
            "not an end-to-end generation test",
        ]
        readiness = "ready"

        if selected is not None and env is not None:
            if configured_provider_invalid:
                checks.append("configured provider: invalid")
                checks.append(f"expected provider: {row.name}")
                readiness = "blocked"
            elif configured_provider is not None:
                checks.append(f"configured provider: {configured_provider}")
                if configured_provider != row.name:
                    checks.append(f"expected provider: {row.name}")
                    readiness = "blocked"

        if row.name == "offline-marker":
            checks.append("api key: not required")
            checks.append("dependency: built-in")
        elif row.name in {"openai-compatible", "deepseek"}:
            checks.append(f"openai package: {'present' if has_openai else 'missing'}")
            key_name = api_key_env
            if key_name is None:
                key_name = {
                    "openai-compatible": "OPENAI_API_KEY",
                    "deepseek": "DEEPSEEK_API_KEY",
                                }[row.name]
            key_present = _env_has(resolved_env, key_name)
            checks.append(f"{key_name}: {'present' if key_present else 'missing'}")
            url_valid = _url_ok(base_url)
            checks.append(f"base_url: {'valid' if url_valid else 'invalid'}")
            if not has_openai or not key_present or not url_valid:
                readiness = "blocked"
        elif row.name == "ollama":
            resolved_base_url = base_url or "http://127.0.0.1:11434"
            url_valid = _url_ok(resolved_base_url)
            checks.append(f"base_url: {'valid' if url_valid else 'invalid'}")
            checks.append(f"model: {'set' if (model or 'qwen2.5:3b').strip() else 'missing'}")
            notes.append("local Ollama server/model not pinged")
            readiness = "unknown" if url_valid else "blocked"
        else:  # pragma: no cover - list_providers controls this set.
            readiness = "blocked"
            checks.append("unknown built-in provider")

        results.append(
            ProviderDoctorRow(
                name=row.name,
                kind=row.kind,
                readiness=readiness,
                checks="; ".join(checks),
                notes="; ".join(notes),
            )
        )
    return results


def list_providers() -> list[ProviderInfo]:
    """Return availability information for the built-in providers.

    The check is import-based: ``status=optional`` means the optional
    dependency is importable; ``status=missing`` means it is not. We do NOT
    ping external services (ollama server, etc.) from this command.
    """
    rows: list[ProviderInfo] = [
        ProviderInfo(
            name="offline-marker",
            kind="offline",
            status="always",
            notes="no API key required",
        ),
        ProviderInfo(
            name="openai-compatible",
            kind="openai_compat",
            status="optional" if _openai_compat_available() else "missing",
            notes="requires [llm] extra (openai package)",
        ),
        ProviderInfo(
            name="deepseek",
            kind="openai_compat",
            status="optional" if _openai_compat_available() else "missing",
            notes="requires [llm] extra and DEEPSEEK_API_KEY; default model deepseek-v4-flash",
        ),
        ProviderInfo(
            name="ollama",
            kind="ollama",
            status="optional",
            notes="requires local Ollama server and qwen2.5:3b (or override --model)",
        ),
    ]
    return rows


def render_providers_table(rows: list[ProviderInfo]) -> str:
    headers = ("NAME", "KIND", "STATUS", "NOTES")
    data = [(r.name, r.kind, r.status, r.notes) for r in rows]
    widths = [max(len(headers[i]), max(len(row[i]) for row in data)) for i in range(len(headers))]

    def line(values: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[i]) for i, value in enumerate(values))

    lines = [line(headers), line(tuple("-" * w for w in widths))]
    for row in data:
        lines.append(line(row))
    return "\n".join(lines) + "\n"


def render_provider_doctor_table(rows: list[ProviderDoctorRow]) -> str:
    headers = ("NAME", "KIND", "READINESS", "CHECKS", "NOTES")
    data = [(r.name, r.kind, r.readiness, r.checks, r.notes) for r in rows]
    widths = [max(len(headers[i]), max(len(row[i]) for row in data)) for i in range(len(headers))]

    def line(values: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[i]) for i, value in enumerate(values))

    lines = [line(headers), line(tuple("-" * w for w in widths))]
    for row in data:
        lines.append(line(row))
    return "\n".join(lines) + "\n"


def render_provider_fix_plan(rows: list[ProviderDoctorRow], *, env_files: list[Path] | None = None) -> str:
    lines = [
        "# Hermes Ershov provider fix plan",
        "",
        "Secret values are never printed. Apply these steps only in the intended operator environment.",
        "",
    ]
    if env_files:
        lines.extend(["## Env files inspected", ""])
        for path in env_files:
            lines.append(f"- `{path}`")
        lines.append("")

    for row in rows:
        lines.extend([f"## {row.name}", "", f"- Readiness: `{row.readiness}`"])
        if row.readiness == "ready":
            lines.extend(["- Config action: none required.", ""])
            continue

        lines.append(f"- Required provider selector: `HERMES_ERSHOV_PROVIDER={row.name}`")
        key_env = PROVIDER_API_KEY_ENVS.get(row.name)
        if key_env is not None:
            lines.append(f"- Required secret: `{key_env}=<secret>`")
        elif row.name == "offline-marker":
            lines.append("- Required secret: none")
        elif row.name == "ollama":
            lines.append("- Required service: local Ollama server with the configured model")

        model = PROVIDER_DEFAULT_MODELS.get(row.name)
        base_url = PROVIDER_DEFAULT_BASE_URLS.get(row.name)
        if row.name != "offline-marker":
            command = f"hermes ershov install-systemd --provider {row.name}"
            if model:
                command += f" --model {model}"
            if base_url:
                command += f" --base-url {base_url}"
            label = "Non-secret env refresh"
            if "<" in command or ">" in command:
                label += " (replace placeholders)"
            lines.append(f"- {label}: `{command}`")
        if key_env is not None:
            lines.append("- Put the secret in the systemd secret env file, not in shell history or release docs.")
        lines.extend(
            [
                f"- Recheck: `hermes ershov providers doctor --provider {row.name} --from-systemd --strict`",
                f"- Then wait for a real scheduled timer run and recheck: `hermes ershov soak --state-root ~/.hermes/ershov --since-hours 30 --min-successful 1 --strict-systemd --require-provider {row.name}`",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def render_provider_doctor_json(rows: list[ProviderDoctorRow]) -> str:
    return json.dumps([asdict(row) for row in rows], ensure_ascii=False, sort_keys=True, indent=2) + "\n"
