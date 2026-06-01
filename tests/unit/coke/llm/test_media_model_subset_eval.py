from __future__ import annotations

import json
import subprocess
from pathlib import Path


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_media_subset_eval_requires_30_to_50_cases_per_manifest(tmp_path):
    asr_manifest = tmp_path / "asr.jsonl"
    vision_manifest = tmp_path / "vision.jsonl"
    write_jsonl(
        asr_manifest,
        [
            {
                "id": f"asr-{index:02d}",
                "storage_uri": "data:audio/wav;base64,UklGRg==",
                "expected_text": "remind me at nine",
            }
            for index in range(29)
        ],
    )
    write_jsonl(
        vision_manifest,
        [
            {
                "id": f"vision-{index:02d}",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "expected_text": "receipt total",
            }
            for index in range(30)
        ],
    )

    result = subprocess.run(
        [
            "scripts/eval-media-model-subset",
            "--asr-model",
            "sensevoice-candidate",
            "--vision-model",
            "qwen-vl-candidate",
            "--asr-manifest",
            str(asr_manifest),
            "--vision-manifest",
            str(vision_manifest),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "asr manifest must contain 30-50 cases" in result.stderr


def test_media_subset_eval_accepts_config_driven_candidate_models(tmp_path):
    asr_manifest = tmp_path / "asr.jsonl"
    vision_manifest = tmp_path / "vision.jsonl"
    write_jsonl(
        asr_manifest,
        [
            {
                "id": f"asr-{index:02d}",
                "storage_uri": "data:audio/wav;base64,UklGRg==",
                "expected_text": "remind me at nine",
            }
            for index in range(30)
        ],
    )
    write_jsonl(
        vision_manifest,
        [
            {
                "id": f"vision-{index:02d}",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "expected_text": "receipt total",
            }
            for index in range(30)
        ],
    )

    result = subprocess.run(
        [
            "scripts/eval-media-model-subset",
            "--asr-model",
            "sensevoice-candidate",
            "--vision-model",
            "qwen-vl-candidate",
            "--asr-manifest",
            str(asr_manifest),
            "--vision-manifest",
            str(vision_manifest),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "asr_model=sensevoice-candidate cases=30" in result.stdout
    assert "vision_model=qwen-vl-candidate cases=30" in result.stdout
