"""Durable reservations for uploaded sources; object I/O happens outside DB locks."""

from datetime import timedelta
from sqlalchemy import select
from browsergrid.models import Bundle, now, uid


class BundleUploadExpired(Exception):
    pass


def reserve(db, project_id, size):
    identifier = uid()
    bundle = Bundle(
        id=identifier,
        project_id=project_id,
        key=f"bundles/{project_id}/{identifier}.zip",
        size=size,
        ready=False,
        expires_at=now() + timedelta(hours=1),
    )
    db.add(bundle)
    db.commit()
    return bundle


def complete(db, identifier):
    bundle = db.scalar(
        select(Bundle)
        .where(Bundle.id == identifier, Bundle.ready.is_(False), Bundle.expires_at > now())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if bundle is None:
        db.rollback()
        raise BundleUploadExpired("Upload reservation expired or was removed")
    bundle.ready = True
    bundle.expires_at = None
    db.commit()
    return bundle
