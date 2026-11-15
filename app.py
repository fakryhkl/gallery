"""GitHub Photo Gallery — Streamlit UI. See SPEC.md; uses logic.py."""

import os
import time

import streamlit as st

from logic import (
    MAX_UPLOAD_MB,
    GitHubClient,
    GitHubError,
    SpecError,
    format_size,
    parse_config,
    total_photo_size,
    validate_uploads,
)

st.set_page_config(page_title="Galery Foto", page_icon="🌸", layout="wide")

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@400;500;600;700&display=swap');

html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp span,
.stApp input, .stApp button, .stApp textarea, .stApp h1, .stApp h2, .stApp h3 {
  font-family: 'Quicksand', 'Trebuchet MS', 'Segoe UI', sans-serif !important;
}

.stApp {
  background:
    radial-gradient(1100px 550px at 8% -8%, #ffe9f5 0%, rgba(255, 233, 245, 0) 60%),
    radial-gradient(900px 500px at 105% 8%, #ffd6ec 0%, rgba(255, 214, 236, 0) 55%),
    linear-gradient(165deg, #fffaFC 0%, #fff0f7 42%, #ffe0f1 100%) !important;
  background-attachment: fixed;
}

::selection { background: #ffc3dd; color: #4a2740; }

.stApp h1 {
  background: linear-gradient(95deg, #ff2e88 0%, #ff7ab8 50%, #ff4f9a 100%);
  -webkit-background-clip: text !important;
  background-clip: text !important;
  color: transparent !important;
  font-weight: 800 !important;
  letter-spacing: 0.4px;
}

.stApp h2, .stApp h3 {
  color: #e2559b !important;
  font-weight: 700 !important;
}

a { color: #e2559b !important; font-weight: 600; }

/* ---------- falling petals ---------- */
.petals {
  position: fixed; inset: 0; pointer-events: none;
  overflow: hidden; z-index: 9999;
}
.petal {
  position: absolute; top: -6vh; font-size: 20px; opacity: 0;
  animation-name: petalFall; animation-timing-function: linear;
  animation-iteration-count: infinite; will-change: transform;
  text-shadow: 0 2px 6px rgba(255, 79, 154, 0.25);
}
@keyframes petalFall {
  0%   { transform: translate3d(0, -8vh, 0) rotate(0deg); opacity: 0; }
  8%   { opacity: 0.8; }
  92%  { opacity: 0.6; }
  100% { transform: translate3d(6vw, 108vh, 0) rotate(340deg); opacity: 0; }
}

/* ---------- buttons ---------- */
.stButton button {
  border-radius: 999px !important;
  font-weight: 700 !important;
  border: 1.5px solid #ffb3d4 !important;
  background: #ffffff !important;
  color: #d63384 !important;
  transition: transform 0.16s ease, box-shadow 0.16s ease,
              background 0.16s ease, border-color 0.16s ease !important;
}
.stButton button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgba(255, 79, 154, 0.3);
  border-color: #ff4f9a !important;
  background: #fff5fa !important;
}
.stButton button:active:not(:disabled) { transform: translateY(0) scale(0.97); }
.stButton button:disabled { opacity: 0.55; transform: none !important; box-shadow: none !important; }
.stButton button[data-testid="stBaseButton-primary"],
.stButton button[kind="primary"] {
  background: linear-gradient(135deg, #ff4f9a 0%, #ff8ac2 100%) !important;
  color: #ffffff !important;
  border: none !important;
}
.stButton button[data-testid="stBaseButton-primary"]:hover:not(:disabled),
.stButton button[kind="primary"]:hover:not(:disabled) {
  background: linear-gradient(135deg, #ff2e88 0%, #ff74b6 100%) !important;
  box-shadow: 0 10px 22px rgba(255, 46, 136, 0.4);
}

/* ---------- inputs ---------- */
div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {
  border-radius: 14px !important;
  border: 1.5px solid #ffc9e2 !important;
  background: #fffafd !important;
  color: #4a2740 !important;
}
div[data-testid="stTextInput"] input::placeholder { color: #e8a4c4; }
div[data-testid="stTextInput"] input:hover { border-color: #ff9ec9 !important; }
div[data-testid="stTextInput"] input:focus {
  border-color: #ff4f9a !important;
  box-shadow: 0 0 0 4px rgba(255, 79, 154, 0.16) !important;
}

/* ---------- uploader ---------- */
div[data-testid="stFileUploaderDropzone"] {
  border-radius: 18px !important;
  border: 2px dashed #ff9ec9 !important;
  background: rgba(255, 255, 255, 0.65) !important;
  transition: background 0.18s ease, border-color 0.18s ease;
}
div[data-testid="stFileUploaderDropzone"]:hover {
  background: #ffeef8 !important;
  border-color: #ff4f9a !important;
}

/* ---------- alerts ---------- */
div[data-testid="stAlert"] {
  border-radius: 16px !important;
  background: rgba(255, 255, 255, 0.88) !important;
  border: 1.5px solid #ffd0e5 !important;
  font-weight: 600;
}

/* ---------- captions / spinner / checkbox ---------- */
[data-testid="stCaptionContainer"] p { color: #b0578a !important; }
[data-testid="stSpinner"] p {
  color: #d63384 !important;
  font-weight: 700 !important;
  font-size: 17px !important;
}
div[data-testid="stCheckbox"] p, div[data-testid="stCheckbox"] label {
  color: #c2306f !important;
  font-weight: 600;
}

/* ---------- metrics ---------- */
div[data-testid="stMetric"] {
  background: rgba(255, 255, 255, 0.82);
  border: 1.5px solid #ffc9e2;
  border-radius: 16px;
  padding: 10px 14px;
  box-shadow: 0 6px 16px rgba(255, 111, 174, 0.12);
}
div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] p {
  color: #d63384 !important;
  font-weight: 700 !important;
}
div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {
  color: #ff2e88 !important;
  font-weight: 800 !important;
}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #ffe6f2 0%, #fff7fb 60%, #ffeff8 100%) !important;
  border-right: 1.5px solid #ffd0e5 !important;
}

/* ---------- expander ---------- */
div[data-testid="stExpander"], details[data-testid="stExpander"] {
  background: rgba(255, 255, 255, 0.72) !important;
  border: 1.5px solid #ffc9e2 !important;
  border-radius: 14px !important;
}
div[data-testid="stExpander"] summary, details summary {
  color: #d63384 !important;
  font-weight: 700 !important;
}

/* ---------- misc ---------- */
.stApp hr {
  border: none !important;
  border-top: 1.5px solid #ffd0e5 !important;
}
.stApp h1 p, .stApp h2 p, .stApp h3 p { color: inherit !important; }

/* ---------- hero card ---------- */
.hero {
  text-align: center;
  padding: 38px 24px 32px;
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.93), rgba(255, 226, 240, 0.93));
  border: 2px solid #ffd0e5;
  box-shadow: 0 18px 44px rgba(255, 79, 154, 0.18);
  margin: 6px 0 4px 0;
}
.hero-emoji {
  font-size: 66px; line-height: 1; display: inline-block;
  animation: heroFloat 2.6s ease-in-out infinite;
  filter: drop-shadow(0 10px 22px rgba(255, 79, 154, 0.35));
}
@keyframes heroFloat {
  0%, 100% { transform: translateY(0) rotate(-4deg); }
  50%      { transform: translateY(-12px) rotate(4deg); }
}
.hero-title {
  margin-top: 16px;
  font-size: 32px; font-weight: 800; letter-spacing: 0.5px;
  background: linear-gradient(95deg, #ff2e88, #ff7ab8);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.hero-sub {
  margin-top: 8px;
  color: #b0487c; font-weight: 600; font-size: 17px;
}

/* ---------- boot splash ---------- */
.boot-screen {
  position: fixed; inset: 0; z-index: 9999999;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
  background:
    radial-gradient(800px 500px at 50% 30%, #fff3f9 0%, #ffe0f0 55%, #ffd0e8 100%);
}
.boot-flower {
  font-size: 96px;
  animation: bootSpin 1.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  filter: drop-shadow(0 12px 30px rgba(255, 79, 154, 0.45));
}
@keyframes bootSpin {
  0%   { transform: rotate(0deg) scale(1); }
  50%  { transform: rotate(180deg) scale(1.18); }
  100% { transform: rotate(360deg) scale(1); }
}
.boot-text {
  margin-top: 24px;
  font-size: 24px; font-weight: 700; color: #d63384;
  letter-spacing: 0.6px;
}
.boot-dots {
  margin-top: 8px;
  font-size: 30px; font-weight: 800; color: #ff4f9a;
}
.boot-dots span {
  display: inline-block;
  animation: bootBlink 1.1s ease-in-out infinite;
}
.boot-dots span:nth-child(2) { animation-delay: 0.18s; }
.boot-dots span:nth-child(3) { animation-delay: 0.36s; }
@keyframes bootBlink {
  0%, 100% { opacity: 0.15; transform: translateY(0); }
  50%      { opacity: 1; transform: translateY(-7px); }
}
</style>
"""

BOOT_HTML = """
<div class="boot-screen">
  <div class="boot-flower">🌸</div>
  <div class="boot-text">Sabar ya dede lagi load</div>
  <div class="boot-dots"><span>.</span><span>.</span><span>.</span></div>
</div>
"""

PETAL_SPECS = (
    (4, 12, 0), (12, 15, 3), (22, 11, 7), (33, 16, 1), (41, 13, 9),
    (52, 14, 5), (61, 12, 11), (70, 15, 2), (79, 11, 8), (88, 16, 4),
    (95, 13, 12), (17, 14, 14), (47, 12, 6), (66, 15, 10),
)
PETAL_EMOJIS = ("D", "E", "A", "F","I","T","A")


def petal_rain():
    spans = "".join(
        f'<span class="petal" style="left:{left}%;'
        f"animation-duration:{dur}s;animation-delay:-{delay}s\">"
        f"{PETAL_EMOJIS[i % len(PETAL_EMOJIS)]}</span>"
        for i, (left, dur, delay) in enumerate(PETAL_SPECS)
    )
    st.markdown(
        f'<div class="petals" aria-hidden="true">{spans}</div>',
        unsafe_allow_html=True,
    )


st.markdown(APP_CSS, unsafe_allow_html=True)

if "booted" not in st.session_state:
    st.markdown(BOOT_HTML, unsafe_allow_html=True)
    time.sleep(1.3)
    st.session_state.booted = True
    st.rerun()

petal_rain()


def get_token():
    raw = (st.session_state.get("token_input") or "").strip()
    if not raw:
        raw = (os.environ.get("GITHUB_TOKEN") or "").strip()
    return raw or None


def show_error(exc):
    message = str(exc)
    if isinstance(exc, GitHubError) and exc.status == 404 and not get_token():
        message += "yah reponya private, masukin token githubnya di sidebar biar bisa liat fotonya"
    st.error(message)


def refresh_photos(client):
    cfg = st.session_state.get("cfg")
    if not cfg:
        return
    try:
        with st.spinner("meloading ulang reponya, sabarrr "):
            st.session_state.photos = client.list_photos(
                cfg.owner, cfg.repo, cfg.subdir, st.session_state.get("branch")
            )
    except GitHubError as exc:
        show_error(exc)


def connect(repo_text, branch_text, subdir_text):
    token = get_token()
    try:
        cfg = parse_config(repo_text, branch_text, subdir_text, token)
        client = GitHubClient(token=token)
        with st.spinner("menyalin repo githubnya… sabar ya..."):
            meta = client.get_repo(cfg.owner, cfg.repo)
            branch = cfg.branch or str(meta.get("default_branch") or "")
            if not branch:
                raise GitHubError("repositorynya g punya branch default, aneh sih")
            photos = client.list_photos(cfg.owner, cfg.repo, cfg.subdir, branch)
    except (SpecError, GitHubError) as exc:
        show_error(exc)
        return
    st.session_state.cfg = cfg
    st.session_state.branch = branch
    st.session_state.photos = photos
    st.session_state.visibility = "Private" if meta.get("private") else "Public"
    st.session_state.connected = True
    st.session_state.edit_photo = None
    st.session_state.pending_delete = None


def do_upload(files, convert=False):
    cfg = st.session_state.get("cfg")
    if not cfg:
        return
    payloads = [(f.name, f.getvalue()) for f in files]
    try:
        validate_uploads([(name, len(data)) for name, data in payloads])
    except SpecError as exc:
        show_error(exc)
        return
    client = GitHubClient(token=get_token())
    branch = st.session_state.get("branch")
    existing = [p.name for p in st.session_state.get("photos") or []]
    uploader = client.upload_thumbnail if convert else client.upload_photo
    try:
        with st.spinner("mengupload foto ke github…"):
            for name, data in payloads:
                path = uploader(
                    cfg.owner,
                    cfg.repo,
                    cfg.subdir,
                    name,
                    data,
                    branch=branch,
                    existing_names=existing,
                )
                existing.append(path.rsplit("/", 1)[-1])
    except (SpecError, GitHubError) as exc:
        show_error(exc)
        refresh_photos(client)
        return
    refresh_photos(client)
    st.session_state.upload_seq += 1
    if convert:
        st.success(f"ngirim {len(payloads)} fotonya sudah 128×128 jadi kecil")
    else:
        st.success(f"ngirim {len(payloads)} foto")


def do_rename(photo, new_name):
    client = GitHubClient(token=get_token())
    cfg = st.session_state.get("cfg")
    try:
        with st.spinner("✨ mengganti namanya…"):
            client.rename_photo(
                cfg.owner,
                cfg.repo,
                photo,
                new_name,
                branch=st.session_state.get("branch"),
                existing_names=[p.name for p in st.session_state.get("photos") or []],
            )
    except (SpecError, GitHubError) as exc:
        show_error(exc)
        return
    st.session_state.pop(f"name_{photo.path}", None)
    st.session_state.edit_photo = None
    st.session_state.flash = f"mengganti nama “{new_name}” berhasil"
    st.rerun()


def do_delete(photo):
    client = GitHubClient(token=get_token())
    cfg = st.session_state.get("cfg")
    try:
        with st.spinner("menghapus fotonya…"):
            client.delete_photo(
                cfg.owner,
                cfg.repo,
                photo,
                branch=st.session_state.get("branch"),
            )
    except GitHubError as exc:
        show_error(exc)
        return
    st.session_state.pending_delete = None
    st.session_state.flash = f"{photo.name} sudah terhapus"
    st.rerun()


def render_card(photo):
    with st.container(border=True):
        st.image(photo.download_url, width="stretch")
        st.caption(f"{photo.name} · {format_size(photo.size or 0)}")
        editing = st.session_state.get("edit_photo") == photo.path
        confirming = st.session_state.get("pending_delete") == photo.path
        if editing:
            st.text_input("ganti nama", key=f"name_{photo.path}")
            c1, c2, c3 = st.columns(3)
            if c1.button("udh", key=f"save_{photo.path}", type="primary", width="stretch"):
                do_rename(photo, (st.session_state.get(f"name_{photo.path}") or "").strip())
            if c2.button("gajadi", key=f"cancel_{photo.path}", width="stretch"):
                st.session_state.pop(f"name_{photo.path}", None)
                st.session_state.edit_photo = None
            if c3.button("buang", key=f"rm_{photo.path}", width="stretch"):
                st.session_state.edit_photo = None
                st.session_state.pending_delete = photo.path
        elif confirming:
            st.warning("fotonya mau dihapus beneran ta? gbisa dibalikin lagi loh")
            c1, c2 = st.columns(2)
            if c1.button("iyah gapapa", key=f"confirm_{photo.path}", type="primary", width="stretch"):
                do_delete(photo)
            if c2.button("eh jangan deh", key=f"dcancel_{photo.path}", width="stretch"):
                st.session_state.pending_delete = None
        else:
            if st.button(
                "edit",
                key=f"edit_{photo.path}",
                help="ganti nama atau hapus fotonya",
                width="stretch",
            ):
                st.session_state.edit_photo = photo.path
                st.session_state[f"name_{photo.path}"] = photo.name


flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

st.title("Galery Foto 🌸")
st.caption("Galeri ini biar lebih mudah uploadnya")

if not st.session_state.get("connected"):
    st.markdown(
        """
<div class="hero">
  <div class="hero-emoji">🌸</div>
  <div class="hero-title">Hi dede, mat datang. </div>
  <div class="hero-sub">Dibawah ini kayak galeri onlinenya ya. km bisa edit, nambah foto atau bahkan hapus foto</div>
</div>
""",
        unsafe_allow_html=True,
    )

with st.container(border=True):
    st.subheader("Taruh Repository Githubnya disini ya dede.")
    repo_text = st.text_input(
        "Repository",
        placeholder="username/repo-nama, misal: dede/galeri-foto atau pake github url lengkapnya",
        key="repo_input",
    )
    b1, b2 = st.columns(2)
    branch_text = b1.text_input("branch (buat kosong aja klo di main)", key="branch_input")
    subdir_text = b2.text_input("subfolder (optional)", key="subdir_input")
    if st.button("Connect", type="primary"):
        connect(repo_text, branch_text, subdir_text)

    if st.session_state.get("connected"):
        cfg = st.session_state.cfg
        visibility = st.session_state.get("visibility", "Public")
        icon = "🌐 public" if visibility == "Public" else "🔒 private"
        st.success(
            f"Ini sudah terhubung dengan 🌸 **{cfg.owner}/{cfg.repo}**"
            f" · branch `{st.session_state.branch}` · {icon}"
        )
    else:
        st.caption("Belum tersambung ke repo github, isi form diatas dan klik connect ya")

with st.container(border=True):
    st.subheader("Upload Foto Disini yaa 📷")
    if "upload_seq" not in st.session_state:
        st.session_state.upload_seq = 0
    uploaded = st.file_uploader(
        f"Drop atau upload foto(jpg, jpeg, png, gif, webp dengan max {MAX_UPLOAD_MB} MB per foto)",
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.upload_seq}",
    )
    convert_toggle = st.checkbox(
        "convert ke 128×128 jpg otomatis(< 16 KB) sebelum upload 📦",
        value=False,
        key="convert_thumbs",
        help=(
            "ini untuk mengecilkan ukuran foto biar pas dilayar ya "
            "dan fotonya dijadiin ke .jpg biar sesuai aja"
        ),
    )
    upload_clicked = st.button(
        "upload ke github 🚀",
        type="primary",
        disabled=not st.session_state.get("connected"),
        width="stretch",
    )
    if upload_clicked:
        if not uploaded:
            st.warning("Upload dulu fotonya dede, baru klik upload yaa")
        else:
            do_upload(uploaded, convert=convert_toggle)
    if not st.session_state.get("connected"):
        st.caption("connect ke repo dulu baru bisa upload ya dede")

with st.container(border=True):
    photos = list(st.session_state.get("photos") or [])
    st.subheader(f"🌸 Galerry ({len(photos)})")
    if photos:
        st.caption(f"total sizenya = {format_size(total_photo_size(photos))} keren")
    if not st.session_state.get("connected"):
        st.info("Connect ke repo dulu biar bisa liat fotonya dede 🌸")
    elif not photos:
        st.info("blm ada foto di repo ini, upload dulu biar muncul")
    else:
        if st.session_state.get("visibility") == "Private":
            st.caption(
                "yah reponya private, pake token di sidebar ya biar bisa liat fotonya"
            )
        columns = st.columns(3)
        for index, photo in enumerate(photos):
            with columns[index % 3]:
                render_card(photo)

st.sidebar.title("Gallery dede")
st.sidebar.caption("Website untuk mempermudah dede")
st.sidebar.text_input(
    "github token ",
    type="password",
    key="token_input",
    help=(
        "ini kalau reponya private, masukin token githubnya disini ya dede. "
        "kalau mau upload foto juga harus ada tokennya ya walau reponya public. "
        "caranya ada di paling bawah, klik aja 'cara ambil token 🎫' biar tau caranya"
    ),
)
with st.expander("cara ambil token 🎫"):
    st.markdown(
        """
**fine-grained token (caranya):**

1. pergi ke <https://github.com/settings/tokens>
2. **Generate new token** → **Fine-grained token**
3. namain terserah, waktu expired terserah, tapi jangan lupa centang **repo** scope
4. **Repository access** → *Only select repositories* (or *All repositories*)
5. **Permissions** → **Contents** → **Read and write** (skip this and uploads flop)
6. lalu pencet **Generate token** terus copy tokennya ya, github cuma nampilin sekali doang tokennya soalnya
7. terus paste ke **github token 🔑** box dikiri atas ya

**classic token (old school but works):**

1. pergi ke <https://github.com/settings/tokens>
2. **Generate new token (classic)**
3. lalu pencet **repo** scope → **Generate token**
4. salin tokennya terus paste ke **github token 🔑** box dikiri atas ya

⚠️ repo public bisa tanpa token, tp cuma buat liat foto aja, kalau mau upload foto juga harus ada tokennya, kalau reponya private ya harus ada tokennya juga biar bisa liat fotonya.
"""
    )
st.sidebar.divider()
st.sidebar.metric(
    "Foto di repo",
    len(st.session_state.get("photos") or [])
    if st.session_state.get("connected")
    else 0,
)
st.sidebar.metric(
    "Storage yang dipakai",
    format_size(total_photo_size(st.session_state.get("photos") or []))
    if st.session_state.get("connected")
    else "0 B",
)
if st.sidebar.button(
    "↻ refresh",
    disabled=not st.session_state.get("connected"),
    width="stretch",
):
    refresh_photos(GitHubClient(token=get_token()))
