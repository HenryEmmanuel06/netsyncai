"""Consistent HTTP error constructors."""

from __future__ import annotations

from fastapi import HTTPException, status


def _err(code: int, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": message})


def http_401(message: str) -> HTTPException:
    return _err(status.HTTP_401_UNAUTHORIZED, message)


def http_403(message: str) -> HTTPException:
    return _err(status.HTTP_403_FORBIDDEN, message)


def http_404(message: str) -> HTTPException:
    return _err(status.HTTP_404_NOT_FOUND, message)


def http_409(message: str) -> HTTPException:
    return _err(status.HTTP_409_CONFLICT, message)
