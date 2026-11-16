"""File operation request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RenameRequest(BaseModel):
    path: str = Field(min_length=1)
    new_name: str = Field(min_length=1, max_length=255)


class MoveCopyRequest(BaseModel):
    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)


class MkdirRequest(BaseModel):
    path: str = Field(min_length=1)


class FileEntry(BaseModel):
    name: str
    rel_path: str
    is_dir: bool = False
    ext: str | None = None
    size: int | None = None
    mtime: float | None = None
    file_id: str | None = None


class BrowseResponse(BaseModel):
    path: str
    entries: list[FileEntry]
    roots: list[dict] | None = None   # populated when path == ""


class SearchResponse(BaseModel):
    query: str
    results: list[dict]
