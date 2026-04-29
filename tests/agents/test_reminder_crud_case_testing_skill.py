from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_reminder_crud_skill_documents_drift_guardrails():
    skill = (
        ROOT / ".agents" / "skills" / "reminder-crud-case-testing" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "Drift Guardrails" in skill
    assert "Do not add case-local `Avoid X` prompt rules" in skill
    assert "Do not add `title_variants` as the first response" in skill
    assert "LLM-first" in skill
    assert "Do not add deterministic Python reminder-create fallbacks" in skill
    assert "Isolate eval identities" in skill
    assert "drift report" in skill
