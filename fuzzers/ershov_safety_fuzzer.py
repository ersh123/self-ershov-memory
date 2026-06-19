from __future__ import annotations

import sys

try:
    import atheris
except ModuleNotFoundError:  # pragma: no cover - local smoke path
    atheris = None

if atheris is not None:  # pragma: no cover - ClusterFuzzLite path
    with atheris.instrument_imports():
        from hermes_dreaming.commands.install_systemd import _env_quote, _single_line_unit_value
        from hermes_dreaming.providers import OfflineMarkerProvider
        from hermes_dreaming.scoring import ProposedOp, validate_op
        from hermes_dreaming.validation import _safe_relative_path, validate_memory_op
else:
    from hermes_dreaming.commands.install_systemd import _env_quote, _single_line_unit_value
    from hermes_dreaming.providers import OfflineMarkerProvider
    from hermes_dreaming.scoring import ProposedOp, validate_op
    from hermes_dreaming.validation import _safe_relative_path, validate_memory_op


def _bounded_text(data: bytes) -> str:
    return data[:4096].decode("utf-8", "ignore")


def TestOneInput(data: bytes) -> None:
    text = _bounded_text(data)
    score = (data[0] / 255.0) if data else 0.0
    confidence = (data[1] / 255.0) if len(data) > 1 else 0.0
    op = ("add", "replace", "remove")[data[2] % 3] if len(data) > 2 else "add"

    _safe_relative_path(text)
    _env_quote(text)
    try:
        _single_line_unit_value("fuzz", text)
    except ValueError:
        pass

    OfflineMarkerProvider()._parse_fact_payload(text)
    validate_memory_op(
        op=op,
        target="memory",
        old_text="- old memory" if op in {"replace", "remove"} else None,
        new_text=f"- {text[:120]}" if op in {"add", "replace"} else None,
        reason="fuzz safety surface",
        sources=["fuzz:1"],
        score=score,
        supersession_confidence=confidence,
    )
    validate_op(
        ProposedOp(
            op=op,
            target="memory",
            old_text="- old memory" if op in {"replace", "remove"} else None,
            new_text=f"- {text[:120]}" if op in {"add", "replace"} else None,
            reason="fuzz safety surface",
            sources=["fuzz:1"],
            score=score,
            supersession_confidence=confidence,
        )
    )


def main() -> None:
    if atheris is None:
        for seed in (b"", b"../escape", b'{"fact":"remember staged writes"}', b"line\nbreak", b"sk-not-a-real-secret-000"):
            TestOneInput(seed)
        return
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
