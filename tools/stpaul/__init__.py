"""St. Paul Sunday School curriculum pipeline.

Layout of the pipeline, and where the freeze line falls:

    content/<sunday>/        source of truth. Editable while status: draft.
        |
        |  tools/lint.py     mechanical rule checks (standards/rules.yml)
        |  review app        pastors read and approve
        |  tools/approve.py  records a review against a content hash
        v
    ===== FREEZE LINE =====  approvals/<sunday>.approval.json
        |
        |  tools/build.py    deterministic. No language model runs here.
        v
    dist/<sunday>/           handoff markdown, DOCX, PDF, app export

Everything above the line may be drafted with help. Everything below it
is pure code, so what prints and what the app shows are the same text by
construction rather than by anyone's diligence.
"""

__all__ = ["model", "rules", "hashing", "approval", "render"]
