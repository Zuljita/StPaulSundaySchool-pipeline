"""One block parser, shared by every renderer.

A section body is Markdown. Deciding what each paragraph *is* — a
bullet, a quoted Scripture block, a subhead, a horizontal rule to be
dropped — is a reading of the source, and every renderer has to reach
the same reading or the outputs stop being the same document.

That is not hypothetical. The handouts and the app were two independent
derivations of one text, nobody wrote them to disagree, and nothing made
them agree; 5 of 12 pieces never reached the app and of the 7 that did,
0 matched the print. A second copy of this function is the same shape of
mistake in miniature: DOCX would set a line as a bullet and the site
would set it as a paragraph, and no test would notice.

So it lives here, once, and `sheet` and `site` both import it.
"""

from __future__ import annotations

import re
from typing import Iterator

# No horizontal rules anywhere, including the ones Markdown makes from
# "---". The rule came from the brand standard Core Standards section 5
# retired; the design system that replaced it draws structure with ruled
# edges on real elements and has no free-standing rule either, so every
# renderer still drops these.
RULE = re.compile(r"-{3,}|\*{3,}|_{3,}")

BULLET = re.compile(r"^[-*☐]\s+")


def blocks(body: str) -> Iterator[tuple[str, str]]:
    """Split a section body into (kind, text) pairs.

    Kinds:
      rule       a horizontal rule. Every renderer drops it.
      scripture  a "> " quoted block. Set apart, and always black in print.
      bullet     one item of a "- ", "* " or checkbox list.
      subhead    a "### " heading inside a section.
      body       an ordinary paragraph.
    """
    for raw in re.split(r"\n\s*\n", body):
        block = raw.strip()
        if not block:
            continue
        if RULE.fullmatch(block):
            yield ("rule", block)
        elif block.startswith("> "):
            yield ("scripture", "\n".join(l[2:] for l in block.splitlines()))
        elif block.startswith(("- ", "* ", "☐ ")):
            for line in block.splitlines():
                yield ("bullet", BULLET.sub("", line))
        elif block.startswith("### "):
            yield ("subhead", block[4:])
        else:
            yield ("body", block)
