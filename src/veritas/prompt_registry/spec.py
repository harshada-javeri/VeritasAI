"""Prompt specification — the versioned, owned unit of the registry.

Tracks ``name``, ``version``, ``owner``, ``model`` (the pinned model this prompt
was written and measured against), and ``schema`` (the logical output schema id),
plus the ``system`` instruction and ``template``. Rendering uses ``string.Template``
(``$placeholder``) so JSON braces in a prompt never collide with formatting, and a
missing variable degrades gracefully rather than raising.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Template

from pydantic import BaseModel, ConfigDict, Field


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())

    name: str
    version: str
    owner: str
    model: str
    output_schema: str = Field(alias="schema")
    template: str
    system: str | None = None
    description: str | None = None

    def render(self, variables: Mapping[str, str]) -> str:
        return Template(self.template).safe_substitute(variables)
