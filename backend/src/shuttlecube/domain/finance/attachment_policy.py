from shuttlecube.api.errors import BusinessError

ALLOWED_ATTACHMENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def validate_attachment(media_type: str, size: int) -> None:
    if media_type not in ALLOWED_ATTACHMENT_TYPES:
        raise BusinessError(422, "unsupported_attachment", "仅支持 JPG、PNG 或 WebP 图片")
    if size > MAX_ATTACHMENT_BYTES:
        raise BusinessError(422, "attachment_too_large", "凭证图片不能超过 10 MB")
