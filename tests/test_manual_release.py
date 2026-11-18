"""The shipped manual must have reviewed the implementation it documents."""
from app.project_help import ProjectHelp


def test_shipped_manual_source_provenance_matches_current_files():
    topics = ProjectHelp().catalogue("zh")
    drift = sorted({source["path"] for topic in topics for source in topic["source_files"]
                    if not source["matches_reviewed"]})
    assert not drift, f"Review manual instructions and refresh their source provenance: {drift}"
