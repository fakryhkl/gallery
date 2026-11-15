"""Core logic for the GitHub Photo Gallery (see SPEC.md).

UI-free: pure parsing/validation helpers plus ``GitHubClient``, which talks
to the GitHub Contents API. The HTTP session is injectable so tests can run
without network access.
"""

import base64
import io
import os
import posixpath
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
from PIL import Image, ImageOps

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
JSON_MEDIA_TYPE = "application/vnd.github+json"
RAW_MEDIA_TYPE = "application/vnd.github.raw"

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_MB = 10

THUMBNAIL_SIZE = (128, 128)
MAX_THUMBNAIL_BYTES = 16 * 1024
MAX_THUMBNAIL_KB = 16
THUMBNAIL_QUALITIES = (90, 80, 70, 60, 50, 40, 30, 20, 10, 5, 1)

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# User-facing messages — mirrored in SPEC.md section 5.
MSG_401 = "GitHub rejected the token — check it's valid and not expired."
MSG_403 = "GitHub rate limit hit or SSO required — wait a minute or use a token."
MSG_404 = "Repository or path not found — check the name and your access."
MSG_409 = "Repository changed while updating — press Refresh."
MSG_422_FALLBACK = "GitHub rejected the request."
MSG_NETWORK = "Couldn't reach GitHub — check your connection and retry."
MSG_EMPTY_REPO = "Enter a repository as owner/repo or a GitHub URL."
MSG_REPO_FORMAT = "Use the format owner/repo (for example: octocat/hello-world)."
MSG_REPO_CHARS = (
    "Repository names may only contain letters, digits, '.', '_' and '-'."
)


class SpecError(Exception):
    """Validation/configuration error whose message is safe to show a user."""


class GitHubError(Exception):
    """GitHub API or network failure with a user-safe message."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class AppConfig:
    owner: str
    repo: str
    branch: str | None = None
    subdir: str = ""
    token: str | None = None


@dataclass(frozen=True)
class PhotoEntry:
    name: str
    path: str
    sha: str
    size: int
    download_url: str
    html_url: str

    @classmethod
    def from_api_item(cls, item: Mapping[str, Any]) -> "PhotoEntry":
        return cls(
            name=str(item.get("name", "")),
            path=str(item.get("path", "")),
            sha=str(item.get("sha", "")),
            size=int(item.get("size", 0) or 0),
            download_url=str(item.get("download_url") or ""),
            html_url=str(item.get("html_url") or ""),
        )


# --------------------------------------------------------------------------
# Parsing / validation (SPEC.md F1, F3, F4, section 4)
# --------------------------------------------------------------------------

def parse_repo_box(text: str) -> tuple[str, str]:
    """Parse the repository box into ``(owner, repo)``.

    Accepts ``owner/repo`` or a GitHub URL; extra path segments, empty input,
    or illegal characters raise :class:`SpecError`.
    """
    s = (text or "").strip()
    if not s:
        raise SpecError(MSG_EMPTY_REPO)
    if s[:8].lower() == "https://":
        s = s[8:]
    elif s[:7].lower() == "http://":
        s = s[7:]
    if s[:11].lower() == "github.com/":
        s = s[11:]
    s = s.rstrip("/")
    if s[-4:].lower() == ".git":
        s = s[:-4].rstrip("/")
    parts = s.split("/")
    if len(parts) != 2 or not all(parts):
        raise SpecError(MSG_REPO_FORMAT)
    owner, repo = parts
    if not _NAME_RE.match(owner) or not _NAME_RE.match(repo):
        raise SpecError(MSG_REPO_CHARS)
    return owner, repo


def normalize_subdir(text: str) -> str:
    """Normalize an optional subdirectory: no leading/trailing slashes."""
    s = (text or "").strip().strip("/")
    segments = [seg for seg in s.split("/") if seg]
    for seg in segments:
        if seg in (".", ".."):
            raise SpecError("Subdirectory can't contain '.' or '..'.")
    return "/".join(segments)


def parse_config(
    repo_text: str,
    branch_text: str = "",
    subdir_text: str = "",
    token: str | None = None,
) -> AppConfig:
    owner, repo = parse_repo_box(repo_text)
    branch = (branch_text or "").strip() or None
    subdir = normalize_subdir(subdir_text)
    return AppConfig(owner=owner, repo=repo, branch=branch, subdir=subdir, token=token)


def is_image_name(name: str) -> bool:
    _, ext = os.path.splitext(name or "")
    return ext.lower() in IMAGE_EXTENSIONS


def select_photos(items: Any) -> list[PhotoEntry]:
    """Filter a Contents API payload down to gallery photos, sorted by name."""
    if items is None:
        return []
    if isinstance(items, Mapping):
        items = [items]
    photos = [
        PhotoEntry.from_api_item(item)
        for item in items
        if isinstance(item, Mapping)
        and item.get("type") == "file"
        and is_image_name(str(item.get("name", "")))
    ]
    photos.sort(key=lambda p: p.name)
    return photos


def validate_upload(filename: str, size: int) -> str:
    """Validate one upload; return the cleaned filename or raise SpecError."""
    name = (filename or "").strip()
    if not name:
        raise SpecError("File has no name.")
    if "/" in name or "\\" in name:
        raise SpecError(f"'{name}' must be a plain filename without folders.")
    if not is_image_name(name):
        raise SpecError(
            f"'{name}' is not a supported image (jpg, jpeg, png, gif, webp)."
        )
    if size > MAX_UPLOAD_BYTES:
        raise SpecError(f"'{name}' is larger than the {MAX_UPLOAD_MB} MB limit.")
    return name


def validate_uploads(files: Iterable[tuple[str, int]]) -> list[str]:
    """Validate an entire batch before anything is committed (SPEC F3)."""
    return [validate_upload(filename, size) for filename, size in files]


def validate_rename(
    old_name: str, new_name: str, existing_names: Iterable[str] = ()
) -> str:
    """Validate a rename; return the cleaned new name or raise SpecError."""
    name = (new_name or "").strip()
    if not name:
        raise SpecError("New name can't be empty.")
    if "/" in name or "\\" in name:
        raise SpecError("Name can't contain '/' or '\\'.")
    if not is_image_name(name):
        raise SpecError(
            f"'{name}' is not a supported image (jpg, jpeg, png, gif, webp)."
        )
    if name == old_name:
        raise SpecError("Choose a name different from the current one.")
    if name in set(existing_names):
        raise SpecError(f"'{name}' already exists in this repository.")
    return name


def next_available_name(name: str, existing_names: Iterable[str]) -> str:
    """Return ``name`` or the first free ``stem (n).ext`` variant (SPEC F3)."""
    taken = set(existing_names)
    if name not in taken:
        return name
    stem, ext = os.path.splitext(name)
    n = 1
    while True:
        candidate = f"{stem} ({n}){ext}"
        if candidate not in taken:
            return candidate
        n += 1


def resolve_upload_names(
    new_names: Iterable[str], existing_names: Iterable[str]
) -> list[str]:
    """Assign non-colliding target names for a whole upload batch."""
    taken = set(existing_names)
    resolved = []
    for name in new_names:
        target = next_available_name(name, taken)
        taken.add(target)
        resolved.append(target)
    return resolved


def build_path(subdir: str, name: str) -> str:
    sub = normalize_subdir(subdir)
    return f"{sub}/{name}" if sub else name


# --------------------------------------------------------------------------
# Thumbnail conversion and repository size reporting
# --------------------------------------------------------------------------

def thumbnail_name(filename: str) -> str:
    """Target name for a converted photo: same stem, ``.jpg`` extension."""
    stem = os.path.splitext((filename or "").strip())[0]
    stem = stem or "photo"
    return f"{stem}.jpg"


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    ):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def convert_to_thumbnail(data: bytes, filename: str = "") -> bytes:
    """Convert an image to an exactly 128x128 JPEG smaller than 16 KB.

    Raises SpecError for empty or unrecognized input, or if the image
    somehow stays at or above 16 KB even at the lowest JPEG quality.
    """
    if not data:
        raise SpecError("The file is empty.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (OSError, ValueError) as exc:
        name = filename or "file"
        raise SpecError(f"'{name}' is not a recognized image.") from exc
    img = ImageOps.exif_transpose(img)
    img = _flatten_to_rgb(img)
    img = ImageOps.fit(img, THUMBNAIL_SIZE, method=Image.Resampling.LANCZOS)
    for quality in THUMBNAIL_QUALITIES:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        out = buffer.getvalue()
        if len(out) < MAX_THUMBNAIL_BYTES:
            return out
    raise SpecError("Couldn't compress the image below 16 KB.")


def total_photo_size(photos: Iterable["PhotoEntry"]) -> int:
    """Total bytes used by the photos in a repository listing."""
    return sum(int(photo.size or 0) for photo in photos)


def format_size(nbytes: int) -> str:
    """Human-readable byte size: ``0 B``, ``512 B``, ``1.5 KB``, ``2.1 MB``."""
    n = max(0, int(nbytes))
    if n < 1024:
        return f"{n} B"
    n /= 1024
    if n < 1024:
        return f"{n:.1f} KB"
    n /= 1024
    if n < 1024:
        return f"{n:.1f} MB"
    n /= 1024
    return f"{n:.1f} GB"


def map_error(status: int, payload: Any = None) -> str:
    """Map a GitHub HTTP error to a friendly user message (SPEC section 5)."""
    if status == 401:
        return MSG_401
    if status == 403:
        return MSG_403
    if status == 404:
        return MSG_404
    if status == 409:
        return MSG_409
    if status == 422:
        message = None
        if isinstance(payload, Mapping):
            raw = payload.get("message")
            if isinstance(raw, str):
                message = raw.strip()
        if message:
            return _strip_docs_link(message)
        return MSG_422_FALLBACK
    return f"GitHub error ({status})."


def _strip_docs_link(message: str) -> str:
    idx = message.find(" - http")
    if idx != -1:
        message = message[:idx]
    return message.strip() or MSG_422_FALLBACK


def _safe_json(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _repo_path(owner: str, repo: str) -> str:
    return f"/repos/{quote(str(owner), safe='')}/{quote(str(repo), safe='')}"


def _contents_path(owner: str, repo: str, file_path: str = "") -> str:
    path = _repo_path(owner, repo) + "/contents"
    if file_path:
        path += "/" + quote(str(file_path), safe="/")
    return path


# --------------------------------------------------------------------------
# GitHub client (SPEC.md section 5)
# --------------------------------------------------------------------------

class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        session: Any = None,
        api_root: str = API_ROOT,
    ) -> None:
        self.token = (token or "").strip() or None
        self._session = session if session is not None else requests.Session()
        self.api_root = api_root.rstrip("/")

    def _headers(self, accept: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": accept or JSON_MEDIA_TYPE,
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        accept: str | None = None,
    ) -> Any:
        url = self.api_root + path
        try:
            response = self._session.request(
                method,
                url,
                headers=self._headers(accept),
                params=params,
                json=json_body,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise GitHubError(MSG_NETWORK) from exc
        if response.status_code >= 400:
            payload = _safe_json(response)
            raise GitHubError(
                map_error(response.status_code, payload),
                status=response.status_code,
            )
        return response

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        response = self._send("GET", _repo_path(owner, repo))
        data = _safe_json(response)
        if not isinstance(data, Mapping):
            raise GitHubError(MSG_404, status=404)
        return dict(data)

    def resolve_branch(
        self, owner: str, repo: str, branch: str | None = None
    ) -> str:
        explicit = (branch or "").strip()
        if explicit:
            return explicit
        data = self.get_repo(owner, repo)
        default = data.get("default_branch")
        if not isinstance(default, str) or not default:
            raise GitHubError("Repository has no default branch.")
        return default

    def list_photos(
        self,
        owner: str,
        repo: str,
        subdir: str = "",
        branch: str | None = None,
    ) -> list[PhotoEntry]:
        branch = self.resolve_branch(owner, repo, branch)
        response = self._send(
            "GET",
            _contents_path(owner, repo, normalize_subdir(subdir)),
            params={"ref": branch},
        )
        return select_photos(_safe_json(response))

    def get_file_bytes(
        self,
        owner: str,
        repo: str,
        file_path: str,
        branch: str | None = None,
    ) -> bytes:
        branch = self.resolve_branch(owner, repo, branch)
        response = self._send(
            "GET",
            _contents_path(owner, repo, file_path),
            params={"ref": branch},
            accept=RAW_MEDIA_TYPE,
        )
        return response.content

    def _get_file_sha(
        self,
        owner: str,
        repo: str,
        file_path: str,
        branch: str | None = None,
    ) -> str:
        branch = self.resolve_branch(owner, repo, branch)
        response = self._send(
            "GET", _contents_path(owner, repo, file_path), params={"ref": branch}
        )
        data = _safe_json(response)
        if not isinstance(data, Mapping) or not data.get("sha"):
            raise GitHubError(MSG_404, status=404)
        return str(data["sha"])

    def _create_file(
        self,
        owner: str,
        repo: str,
        file_path: str,
        data: bytes,
        message: str,
        branch: str,
    ) -> None:
        body = {
            "message": message,
            "content": base64.b64encode(data).decode("ascii"),
            "branch": branch,
        }
        try:
            self._send("PUT", _contents_path(owner, repo, file_path), json_body=body)
        except GitHubError as exc:
            if exc.status != 409:
                raise
            # Concurrent change: one automatic retry (SPEC section 5).
            self._send("PUT", _contents_path(owner, repo, file_path), json_body=body)

    def _delete_file(
        self,
        owner: str,
        repo: str,
        file_path: str,
        message: str,
        branch: str,
        sha: str,
    ) -> None:
        body = {"message": message, "sha": sha, "branch": branch}
        try:
            self._send(
                "DELETE", _contents_path(owner, repo, file_path), json_body=body
            )
        except GitHubError as exc:
            if exc.status != 409:
                raise
            fresh_sha = self._get_file_sha(owner, repo, file_path, branch)
            body = {"message": message, "sha": fresh_sha, "branch": branch}
            self._send(
                "DELETE", _contents_path(owner, repo, file_path), json_body=body
            )

    def upload_photo(
        self,
        owner: str,
        repo: str,
        subdir: str,
        filename: str,
        data: bytes,
        branch: str | None = None,
        existing_names: Iterable[str] = (),
    ) -> str:
        """Validate, de-collide, and commit one photo. Returns stored path."""
        name = validate_upload(filename, len(data))
        target = next_available_name(name, existing_names or ())
        file_path = build_path(subdir, target)
        branch = self.resolve_branch(owner, repo, branch)
        self._create_file(
            owner,
            repo,
            file_path,
            data,
            f"Add {target} via photo gallery",
            branch,
        )
        return file_path

    def upload_thumbnail(
        self,
        owner: str,
        repo: str,
        subdir: str,
        filename: str,
        data: bytes,
        branch: str | None = None,
        existing_names: Iterable[str] = (),
    ) -> str:
        """Convert to a 128x128 JPEG (<16 KB) and commit it. Returns stored path.

        No API call is made if conversion fails.
        """
        converted = convert_to_thumbnail(data, filename)
        target = thumbnail_name(filename)
        return self.upload_photo(
            owner,
            repo,
            subdir,
            target,
            converted,
            branch=branch,
            existing_names=existing_names,
        )

    def rename_photo(
        self,
        owner: str,
        repo: str,
        photo: PhotoEntry,
        new_name: str,
        branch: str | None = None,
        existing_names: Iterable[str] = (),
    ) -> str:
        """Validate, fetch bytes, create new file, delete old. Returns new path."""
        target = validate_rename(photo.name, new_name, existing_names)
        directory = posixpath.dirname(photo.path)
        new_path = build_path(directory, target)
        branch = self.resolve_branch(owner, repo, branch)
        data = self.get_file_bytes(owner, repo, photo.path, branch)
        self._create_file(
            owner,
            repo,
            new_path,
            data,
            f"Rename {photo.name} to {target} via photo gallery",
            branch,
        )
        self._delete_file(
            owner,
            repo,
            photo.path,
            f"Delete {photo.name} via photo gallery",
            branch,
            photo.sha,
        )
        return new_path

    def delete_photo(
        self,
        owner: str,
        repo: str,
        photo: PhotoEntry,
        branch: str | None = None,
    ) -> None:
        branch = self.resolve_branch(owner, repo, branch)
        self._delete_file(
            owner,
            repo,
            photo.path,
            f"Delete {photo.name} via photo gallery",
            branch,
            photo.sha,
        )
