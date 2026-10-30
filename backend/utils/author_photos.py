"""Stable, extension-bearing URLs for self-hosted author photos."""

from backend.models.database import Author, AuthorPhoto
from backend.utils.organization_logos import organization_logo_extension


def author_photo_path(photo: AuthorPhoto) -> str:
    extension = organization_logo_extension(photo.mime_type)
    return f"/api/v1/authors/{photo.author_id}/photo/{photo.sha256}.{extension}"


def author_image_url(author: Author, photo: AuthorPhoto | None) -> str | None:
    """The author's face: a stored photo, else an uploaded (non-default) HF avatar."""
    if photo is not None:
        return author_photo_path(photo)
    avatar = author.hf_avatar_url
    if (
        author.hf_username
        and avatar
        and avatar.startswith("https://")
        and not avatar.startswith("https://huggingface.co/avatars/")
    ):
        return avatar
    return None
