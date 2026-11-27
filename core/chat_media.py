"""Photos and videos in chats (v1.1.1, CHG-006) — Messenger style.

Safety
* Only photos (JPG, PNG, WebP) and videos (MP4, MOV, WebM, 3GP, MKV) are accepted, and every
  file is **re-encoded**: photos become JPEG (Pillow), videos become H.264/AAC MP4 (ffmpeg).
  A file that cannot be re-encoded as a real photo/video is refused, so hidden payloads
  ("trojan" files) never reach the other person. Only the re-encoded copy is stored; the
  received file is deleted as soon as processing ends. Chat media are private files served
  only to the two people in the chat and authorized reviewers.

Limits (per file)
* Verified: photo upload <= 5 MB; video <= 20 MB and <= 60 s, stored at 720p (~1 Mbit/s).
  No limit on how many - but a heavy flood in one chat is quietly slowed down
  (uploads wait longer in "Processing...", nothing says "refused").
* Unverified students: photo <= 2 MB; video <= 8 MB and <= 20 s, stored at 480p; at most
  3 photos/videos per chat.

Speed
* Photos are re-encoded right away (well under a second). Videos go to one background
  worker thread; ffmpeg runs as its own program with 2 threads, so the website stays quick.
"""
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import close_old_connections, models, transaction
from django.utils import timezone

from .images import PREVIEW, compress
from .models import ChatAttachment, ChatMessage, ClaimApplication, Conversation

log = logging.getLogger("findit.chat_media")

PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".3gp": "video/3gpp",
               ".mkv": "video/x-matroska", ".m4v": "video/x-m4v"}
MB = 1024 * 1024

LIMITS = {
    "verified": {
        "photo_bytes": 5 * MB, "video_bytes": 20 * MB, "video_seconds": 60,
        "photo": {"max_side": 1600, "max_bytes": 300 * 1024}, "video_side": 1280, "video_kbps": 1000,
        "per_chat": None,
    },
    "unverified": {
        "photo_bytes": 2 * MB, "video_bytes": 8 * MB, "video_seconds": 20,
        "photo": {"max_side": 1280, "max_bytes": 200 * 1024}, "video_side": 854, "video_kbps": 600,
        "per_chat": 3,
    },
}
# Heavy-load slow-down (verified): more than this many MB uploaded by one person in one chat
# within an hour makes further uploads wait longer in "Processing..." (no error is shown).
HEAVY_MB_PER_HOUR = 100
HEAVY_FILES_PER_10_MIN = 30
MAX_SLOWDOWN_SECONDS = 15 * 60
FFMPEG_TIMEOUT_SECONDS = 180
STUCK_AFTER = timedelta(minutes=30)


class MediaRefused(Exception):
    pass


def limits_for(user):
    from .permissions import is_unverified_student
    return LIMITS["unverified" if is_unverified_student(user) else "verified"]


def kind_of(name, content_type=""):
    ext = os.path.splitext(name or "")[1].lower()
    if ext in PHOTO_TYPES:
        return ChatAttachment.Kind.PHOTO
    if ext in VIDEO_TYPES:
        return ChatAttachment.Kind.VIDEO
    return None


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# Accepting an upload
# ---------------------------------------------------------------------------

def accept_upload(conversation, user, uploaded, client_id):
    """Check and store a received file. Returns the ChatAttachment (PROCESSING or READY).
    Raises MediaRefused with a plain reason. A repeat of the same client_id returns the first one."""
    from .verification import blocked_between
    client_id = (client_id or "").strip()[:64]
    if not client_id:
        raise MediaRefused("Missing upload id. Reload the page and try again.")
    existing = ChatAttachment.objects.filter(conversation=conversation, client_id=client_id).first()
    if existing:
        if existing.uploader_id != user.pk:
            raise MediaRefused("This upload could not be sent.")
        return existing
    if not conversation.includes(user) or conversation.is_closed or conversation.is_paused:
        raise MediaRefused("This conversation is not open for new messages.")
    other = conversation.recipient if conversation.initiator_id == user.pk else conversation.initiator
    if blocked_between(user, other):
        raise MediaRefused("This conversation is not open for new messages.")
    kind = kind_of(uploaded.name)
    if kind is None:
        raise MediaRefused("Send a photo (JPG, PNG, WebP) or a video (MP4, MOV, WebM, 3GP, MKV).")
    limits = limits_for(user)
    max_bytes = limits["photo_bytes"] if kind == ChatAttachment.Kind.PHOTO else limits["video_bytes"]
    if uploaded.size > max_bytes:
        who = "Unverified accounts" if limits["per_chat"] else "You"
        raise MediaRefused(f"{who} can send {kind.label.lower()}s up to {max_bytes // MB} MB.")
    if limits["per_chat"] is not None:
        used = ChatAttachment.objects.filter(conversation=conversation, uploader=user).exclude(
            status=ChatAttachment.Status.FAILED).count()
        if used >= limits["per_chat"]:
            raise MediaRefused(f"Unverified accounts can send {limits['per_chat']} photos or videos per chat. "
                               "Verify your email to send more.")
    attachment = ChatAttachment(
        conversation=conversation, uploader=user, client_id=client_id, kind=kind,
        uploaded_bytes=uploaded.size, not_before=timezone.now() + timedelta(seconds=slowdown_seconds(conversation, user)),
    )
    attachment.upload.save(os.path.basename(uploaded.name) or "upload", uploaded, save=False)
    try:
        attachment.save()
    except Exception:
        attachment.upload.delete(save=False)
        again = ChatAttachment.objects.filter(conversation=conversation, client_id=client_id).first()
        if again:
            return again  # the same upload arrived twice at the same moment
        raise
    if kind == ChatAttachment.Kind.PHOTO and attachment.not_before <= timezone.now():
        process(attachment)  # photos are quick: done before the reply
        attachment.refresh_from_db()
    else:
        transaction.on_commit(start_worker)
    return attachment


def slowdown_seconds(conversation, user):
    """Shadow slow-down for heavy loads in one chat (no error, just a longer wait)."""
    now = timezone.now()
    recent = ChatAttachment.objects.filter(conversation=conversation, uploader=user).exclude(
        status=ChatAttachment.Status.FAILED)
    hour_mb = (recent.filter(created_at__gte=now - timedelta(hours=1)).aggregate(
        total=models.Sum("uploaded_bytes"))["total"] or 0) / MB
    ten_min = recent.filter(created_at__gte=now - timedelta(minutes=10)).count()
    wait = 0
    if hour_mb > HEAVY_MB_PER_HOUR:
        wait = max(wait, 30 * (1 + int((hour_mb - HEAVY_MB_PER_HOUR) // 10)))
    if ten_min >= HEAVY_FILES_PER_10_MIN:
        wait = max(wait, 20 * (1 + ten_min - HEAVY_FILES_PER_10_MIN))
    if wait:
        # Queue behind this person's own waiting uploads, so the wait keeps growing.
        last = recent.filter(status=ChatAttachment.Status.PROCESSING).order_by("-not_before").first()
        if last and last.not_before > now:
            wait += int((last.not_before - now).total_seconds())
    return min(wait, MAX_SLOWDOWN_SECONDS)


# ---------------------------------------------------------------------------
# Re-encoding
# ---------------------------------------------------------------------------

def _probe(ffmpeg, path):
    """Duration (s), width, height and whether there is sound, read from ffmpeg's report."""
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True, timeout=30)
    report = result.stderr
    duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", report)
    video = re.search(r"Stream #[^\n]*Video:[^\n]*?(\d{2,5})x(\d{2,5})", report)
    if not duration or not video:
        raise MediaRefused("That file is not a video we can play.")
    seconds = int(duration.group(1)) * 3600 + int(duration.group(2)) * 60 + float(duration.group(3))
    return seconds, int(video.group(1)), int(video.group(2)), "Audio:" in report


def _encode_video(attachment, limits):
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise MediaRefused("Videos cannot be processed on this computer yet (the converter is missing).")
    with tempfile.TemporaryDirectory(prefix="findit-video-") as work:
        source = os.path.join(work, "in" + os.path.splitext(attachment.upload.name)[1])
        with attachment.upload.open("rb") as handle, open(source, "wb") as out:
            shutil.copyfileobj(handle, out)
        seconds, width, height, has_audio = _probe(ffmpeg, source)
        if seconds > limits["video_seconds"] + 0.5:
            raise MediaRefused(f"Videos can be up to {limits['video_seconds']} seconds long.")
        side = limits["video_side"]
        kbps = limits["video_kbps"]
        target = os.path.join(work, "out.mp4")
        scale = f"scale='if(gt(iw,ih),min({side},iw),-2)':'if(gt(iw,ih),-2,min({side},ih))'"
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", source, "-map", "0:v:0"]
        if has_audio:
            command += ["-map", "0:a:0?"]
        command += [
            "-t", str(limits["video_seconds"]), "-vf", scale + ",format=yuv420p", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "28", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k",
            "-threads", "2", "-map_metadata", "-1", "-movflags", "+faststart",
        ]
        command += ["-c:a", "aac", "-b:a", "64k", "-ac", "1"] if has_audio else ["-an"]
        command.append(target)
        done = subprocess.run(command, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS)
        if done.returncode != 0 or not os.path.exists(target) or os.path.getsize(target) == 0:
            raise MediaRefused("That video could not be processed. Try another video.")
        poster = os.path.join(work, "poster.jpg")
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(min(0.5, seconds / 2)),
                        "-i", target, "-frames:v", "1", poster], capture_output=True, timeout=60)
        out_seconds, out_w, out_h, _ = _probe(ffmpeg, target)
        with open(target, "rb") as handle:
            data = handle.read()
        preview = None
        if os.path.exists(poster):
            with open(poster, "rb") as handle:
                preview = compress(io.BytesIO(handle.read()), **PREVIEW)
        return data, preview, out_w, out_h, out_seconds


def _encode_photo(attachment, limits):
    from PIL import Image
    with attachment.upload.open("rb") as handle:
        raw = io.BytesIO(handle.read())
    try:
        full = compress(raw, **limits["photo"])
    except Exception:
        raise MediaRefused("That file is not a photo we can show.")
    preview = compress(io.BytesIO(full), **PREVIEW)
    with Image.open(io.BytesIO(full)) as image:
        width, height = image.size
    return full, preview, width, height, 0


def process(attachment):
    """Re-encode one attachment, then post it as a chat message (or mark it failed)."""
    attachment = ChatAttachment.objects.select_related("uploader", "conversation").get(pk=attachment.pk)
    if attachment.status != ChatAttachment.Status.PROCESSING:
        return attachment
    limits = limits_for(attachment.uploader)
    try:
        if attachment.kind == ChatAttachment.Kind.PHOTO:
            data, preview, width, height, seconds = _encode_photo(attachment, limits)
            name = "photo.jpg"
        else:
            data, preview, width, height, seconds = _encode_video(attachment, limits)
            name = "video.mp4"
    except MediaRefused as exc:
        return _fail(attachment, str(exc))
    except Exception as exc:  # a broken file must never crash the worker
        log.warning("Chat media %s failed: %s", attachment.pk, exc)
        return _fail(attachment, "That file could not be processed.")
    with transaction.atomic():
        attachment.file.save(name, ContentFile(data), save=False)
        if preview:
            attachment.preview.save("preview.jpg", ContentFile(preview), save=False)
        attachment.width, attachment.height, attachment.duration_seconds = width, height, round(seconds, 1)
        attachment.stored_bytes = len(data)
        conversation = Conversation.objects.select_for_update().get(pk=attachment.conversation_id)
        if conversation.is_closed or conversation.is_paused:
            raise_closed = True
        else:
            raise_closed = False
            message = ChatMessage.objects.create(
                conversation=conversation, sender=attachment.uploader, text="",
                client_id=f"att-{attachment.client_id}"[:64],
            )
            attachment.message = message
            attachment.status = ChatAttachment.Status.READY
            attachment.ready_at = timezone.now()
            conversation.save(update_fields=["updated_at"])
            if conversation.claim_id:
                ClaimApplication.objects.filter(pk=conversation.claim_id).update(last_activity_at=timezone.now())
        old_upload = attachment.upload.name
        attachment.upload = ""
        attachment.save()
    _delete_file(old_upload)
    if raise_closed:
        return _fail(attachment, "This conversation closed before the file was sent.")
    _broadcast_message(attachment)
    return attachment


def _fail(attachment, reason):
    old_upload = attachment.upload.name
    ChatAttachment.objects.filter(pk=attachment.pk).update(
        status=ChatAttachment.Status.FAILED, error=reason[:240], upload="",
    )
    _delete_file(old_upload)
    for field in (attachment.file, attachment.preview):
        if field:
            _delete_file(field.name)
    _broadcast_event(attachment, {"event": "attachment_failed", "client_id": attachment.client_id,
                                  "uploader_id": attachment.uploader_id, "error": reason})
    attachment.refresh_from_db()
    return attachment


def _delete_file(name):
    if name:
        try:
            ChatAttachment._meta.get_field("file").storage.delete(name)
        except Exception:
            pass


def attachment_json(attachment):
    from django.urls import reverse
    if attachment is None or attachment.status != ChatAttachment.Status.READY:
        return None
    return {
        "kind": attachment.kind, "width": attachment.width, "height": attachment.height,
        "duration": attachment.duration_seconds, "bytes": attachment.stored_bytes,
        "url": reverse("chat-media", args=[attachment.pk, "file"]),
        "preview_url": reverse("chat-media", args=[attachment.pk, "preview"]) if attachment.preview else "",
    }


def _broadcast_message(attachment):
    message = attachment.message
    payload = {
        "type": "chat.message", "id": message.pk,
        "sender": attachment.uploader.get_full_name() or attachment.uploader.username,
        "sender_id": attachment.uploader_id, "text": "", "sent_at": message.sent_at.isoformat(),
        "client_id": message.client_id, "attachment": attachment_json(attachment),
    }
    _group_send(attachment.conversation_id, payload)


def _broadcast_event(attachment, data):
    _group_send(attachment.conversation_id, {"type": "chat.event", "payload": data})


def _group_send(conversation_id, payload):
    def send():
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(f"conversation_{conversation_id.hex}", payload)
        except Exception:
            pass
    transaction.on_commit(send)


# ---------------------------------------------------------------------------
# Background worker (one thread per web process)
# ---------------------------------------------------------------------------

_worker_lock = threading.Lock()
_worker_wake = threading.Event()
_worker_thread = None


def start_worker():
    global _worker_thread
    _worker_wake.set()
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_worker_loop, name="findit-chat-media", daemon=True)
            _worker_thread.start()


def next_job():
    return ChatAttachment.objects.filter(
        status=ChatAttachment.Status.PROCESSING, not_before__lte=timezone.now(),
    ).order_by("not_before", "created_at").first()


def run_pending(limit=50):
    """Process waiting uploads one by one (also used by tests and the timer runner)."""
    done = 0
    while done < limit:
        job = next_job()
        if job is None:
            break
        process(job)
        done += 1
    return done


def _worker_loop():
    idle_rounds = 0
    while idle_rounds < 60:          # stop after ~5 idle minutes; the next upload restarts it
        _worker_wake.clear()
        close_old_connections()
        try:
            worked = run_pending(limit=5)
        except Exception as exc:
            log.warning("Chat media worker error: %s", exc)
            worked = 0
        finally:
            close_old_connections()
        if worked:
            idle_rounds = 0
            continue
        idle_rounds += 1
        _worker_wake.wait(5)


def fail_stuck_uploads():
    """Timer runner: uploads still processing after 30 minutes are marked failed."""
    cutoff = timezone.now() - STUCK_AFTER
    for job in ChatAttachment.objects.filter(status=ChatAttachment.Status.PROCESSING, not_before__lt=cutoff):
        _fail(job, "That file took too long to process. Try sending it again.")
