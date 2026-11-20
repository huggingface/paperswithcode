# ADR 0011: Thumbnails and images

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Author portrait crops keep the top of tall photos

Author photos are cropped to a square with the vertical offset at one sixth of the spare height rather than centred, because portraits frame the face high in the image. Centring would cut off heads on tall photos.

Code: `backend/database/import_author_photo.py::square_jpeg`

## External downloads accept generic binary content types and verify content

raw.githubusercontent.com and many object stores serve PDFs and images as application/octet-stream or binary/octet-stream. External downloads therefore accept those content types and rely on content checks instead: the %PDF magic bytes for PDFs and Pillow decoding for artwork. Restricting to exact MIME types would reject many legitimate sources.

Some object stores label images as generic binary, so artwork downloads accept octet-stream content types and let Pillow decide whether the bytes are an image.

Code: `backend/services/thumbnail_service.py::EXTERNAL_PDF_CONTENT_TYPES`, `backend/services/thumbnail_service.py::EXTERNAL_ARTWORK_CONTENT_TYPES`

## External fetch allowlist includes redirect-target CDNs

External PDF and artwork downloads follow redirects only to allowlisted hosts. huggingface.co/.../resolve/... redirects LFS and Xet files to HF CDN hosts, and github.com/<owner>/<repo>/raw/... redirects Git LFS files to media.githubusercontent.com, so those CDNs are allowlisted alongside the origin sites. Pruning them as unrecognised would break fetches from the Hub and GitHub LFS.

github.com/<owner>/<repo>/raw/... redirects Git LFS files to media.githubusercontent.com, so that host is allowlisted for external downloads; removing it breaks LFS-hosted PDFs and artwork.

media.eventhosts.cc hosts ECCV conference PDFs referenced by papers.conference_url_pdf and is allowlisted for external PDF downloads; it would otherwise look like an unrelated host to prune.

Code: `backend/services/thumbnail_service.py::EXTERNAL_PDF_HOSTS`

## Generated thumbnails are chmod 0644

The shared thumbnail cache is written by CRON and admin processes but served by the unprivileged production backend under a different service user. Thumbnails are public, so every generated JPEG is explicitly made world-readable rather than inheriting the writer's umask, which could leave files the backend cannot serve.

Code: `backend/services/thumbnail_service.py::ThumbnailService._save_thumbnail`

## PDF thumbnails keep the page's native aspect ratio

Paper cards display thumbnails in a 160x220 box, but PDF pages have their own MediaBox/CropBox ratio (US Letter at width 400 is about 518px tall). PDF thumbnails are rendered at native, variable height and the frontend containment frame absorbs the small difference; only non-PDF fallbacks use the nominal card height. Forcing PDFs to the card ratio would crop or distort pages.

EXPECTED_THUMBNAIL_HEIGHT is the nominal card height used for card-sized non-PDF fallbacks. PDF thumbnails use a native, variable height instead, so this constant must not be used to validate or resize PDF renders.

Code: `backend/services/thumbnail_service.py::CARD_THUMB_ASPECT`, `backend/services/thumbnail_service.py::EXPECTED_THUMBNAIL_HEIGHT`

## Persist external thumbnail URL by checking the ORM row, not the API model

PaperService hydrates the API model's thumbnail_url from the on-disk thumbnail, so it can be set even when the stored papers.thumbnail_url column is empty. The thumbnail endpoint therefore reads the DBPaper row directly to decide whether to backfill the column; checking the API model would skip the write forever.

Code: `backend/routers/thumbnails.py::generate_thumbnail`

## Regenerated thumbnails persist a versioned explicit URL

The API prefers a paper's explicit thumbnail_url over its derived arXiv thumbnail URL. Regeneration writes a URL carrying a per-generation cache-bust token (file mtime) to the paper row, so a new image cannot stay hidden behind browser or CDN caches or an older explicit URL.

Code: `backend/services/paper_thumbnail_service.py::regenerate_paper_thumbnail`

## Sparse-footer cropping is limited to the bottom 5% of the page

Thumbnail rendering strips sparse rows such as copyright lines and page numbers, but only within the bottom 5% of the page. Without that limit, low-density body text like abstract paragraphs looks like a footer and gets cropped away.

Code: `backend/services/thumbnail_service.py::MAX_SPARSE_FOOTER_HEIGHT_FRACTION`

## Task and method images are deferred blobs flagged by mime type

Task hero images and method figures are stored in the database as image_data bytes, mapped with deferred loading so list queries never pull the potentially large blob. The small image_mime_type column is always loaded and serves as the has-a-DB-image flag the API uses to build the /api/v1/tasks/{slug}/image URL. Loading image_data to test presence would defeat the deferral.

Code: `backend/models/database/taxonomy.py::Task`

## Thumbnail artwork filters reject logos, covers and extreme shapes

Paper thumbnails embed artwork from source pages only when it is likely to depict the paper. Images under 200x100 px (favicons, logos, Springer's 153 px proceedings covers) and images wider than 2.6:1 (banners that become an unreadable strip on a portrait card) are rejected, as are generic site images matched by path such as publisher logos (arXiv's arxiv-logo-fb.png) and Springer journal or book covers. Rejected artwork falls back to a title card, which looks better than these images.

Code: `backend/services/thumbnail_artwork.py`

## Thumbnail lookup failures never block paper hydration

Legacy catalog arXiv identifiers can be malformed, making thumbnail path construction raise ThumbnailGenerationError. Because the thumbnail is optional, _resolve_thumbnail_url returns None in that case so a single bad identifier cannot fail hydration of the paper or of a whole card batch.

Code: `backend/services/paper_service.py::PaperService._resolve_thumbnail_url`

## Thumbnail validation only rejects landscape or square renders

Older renders clipped the height and produced squat thumbnails around H/W 0.65. Validation rejects anything below a 1.0 height-to-width ratio to catch those, but stays permissive above it because PDF pages may use custom portrait dimensions.

Code: `backend/services/thumbnail_service.py::MIN_THUMBNAIL_HEIGHT_TO_WIDTH_RATIO`

## Transient external PDF failures raise instead of falling back to a card

When an external paper's PDF URL fails transiently and no archived copy exists, thumbnail generation raises so the job retries later. Falling back to a metadata card would cache a generic thumbnail in place of the real first page and it would not be regenerated.

Code: `backend/services/thumbnail_service.py::ThumbnailService.generate_external_thumbnail`

## bioRxiv/medRxiv PDFs via requester-pays S3 with Europe PMC fallback

bioRxiv and medRxiv full-text PDFs come from their TDM requester-pays S3 bucket, which needs AWS credentials and incurs transfer cost. The credentials are optional: when unset, thumbnail generation falls back to Europe PMC PDF mirrors where available.

Code: `backend/config.py::Settings.biorxiv_aws_access_key_id`
