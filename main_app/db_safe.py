"""Database helpers that avoid 500s when Postgres is down or migrations are behind."""

from __future__ import annotations

import logging

from django.db import DatabaseError

logger = logging.getLogger(__name__)


def safe_first(queryset, default=None):
    try:
        return queryset.first()
    except DatabaseError:
        logger.exception("safe_first failed for %s", queryset.model)
        return default


def safe_count(queryset, default: int = 0) -> int:
    try:
        return queryset.count()
    except DatabaseError:
        logger.exception("safe_count failed for %s", queryset.model)
        return default


def safe_aggregate_sum(queryset, field: str, default: int = 0) -> int:
    try:
        from django.db.models import Sum

        total = queryset.aggregate(total=Sum(field)).get("total")
        return int(total or 0)
    except DatabaseError:
        logger.exception("safe_aggregate_sum failed for %s", queryset.model)
        return default


def safe_list(queryset, default=None):
    if default is None:
        default = []
    try:
        return list(queryset)
    except DatabaseError:
        logger.exception("safe_list failed for %s", queryset.model)
        return default
