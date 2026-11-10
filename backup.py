
import hashlib
import json
import shutil
import tarfile
import time
from datetime import datetime
from pathlib import Path

SOURCE = Path("company_data")
BACKUP_DIR = Path("backups")
KEEP_LAST = 5


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_manifest(folder):
    return {
        str(p.relative_to(folder)): sha256(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def create_backup():
    BACKUP_DIR.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = BACKUP_DIR / f"backup_{stamp}.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(SOURCE, arcname=SOURCE.name)

    manifest = {
        "created": stamp,
        "archive_sha256": sha256(archive),
        "files": make_manifest(SOURCE)
    }

    archive.with_suffix("").with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(
        f"[OK] Создан {archive.name}, "
        f"файлов: {len(manifest['files'])}, "
        f"размер: {archive.stat().st_size / 1024:.1f} КБ"
    )

    return archive


def rotate():
    archives = sorted(BACKUP_DIR.glob("backup_*.tar.gz"))

    for old in archives[:-KEEP_LAST]:
        old.unlink()
        old.with_suffix("").with_suffix(".json").unlink(
            missing_ok=True
        )
        print(f"[ROTATE] Удалена старая копия {old.name}")


def verify_restore(archive):
    manifest = json.loads(
        archive.with_suffix("").with_suffix(".json").read_text(
            encoding="utf-8"
        )
    )

    if sha256(archive) != manifest["archive_sha256"]:
        print("[FAIL] Архив повреждён: контрольная сумма не совпадает")
        return False

    tmp = Path("restore_test")
    shutil.rmtree(tmp, ignore_errors=True)

    with tarfile.open(archive) as tar:
        tar.extractall(tmp, filter="data")

    restored = make_manifest(tmp / SOURCE.name)
    shutil.rmtree(tmp)

    original = manifest["files"]

    if restored == original:
        print(
            f"[OK] Восстановление проверено: "
            f"{len(restored)} файлов совпадают"
        )
        return True

    missing = set(original) - set(restored)
    extra = set(restored) - set(original)

    changed = {
        file for file in original.keys() & restored.keys()
        if original[file] != restored[file]
    }

    for file in sorted(missing):
        print(f"[MISSING] Отсутствует файл: {file}")

    for file in sorted(extra):
        print(f"[EXTRA] Лишний файл: {file}")

    for file in sorted(changed):
        print(f"[CHANGED] Изменён файл: {file}")

    print("[FAIL] Восстановленные данные не совпадают")
    return False


def restore(archive):
    start = time.perf_counter()

    manifest_path = archive.with_suffix("").with_suffix(".json")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    if sha256(archive) != manifest["archive_sha256"]:
        print("[FAIL] Нельзя восстановить: архив повреждён")
        return False

    tmp = Path("restore_test")
    shutil.rmtree(tmp, ignore_errors=True)

    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(tmp, filter="data")

    restored = make_manifest(tmp / SOURCE.name)

    if restored != manifest["files"]:
        shutil.rmtree(tmp, ignore_errors=True)
        print("[FAIL] Файлы в архиве не совпадают с манифестом")
        return False

    shutil.rmtree(SOURCE, ignore_errors=True)
    shutil.move(str(tmp / SOURCE.name), str(SOURCE))
    shutil.rmtree(tmp, ignore_errors=True)

    elapsed = time.perf_counter() - start

    print(f"[OK] Данные восстановлены: {len(restored)} файлов")
    print(f"Время восстановления: {elapsed:.4f} сек.")

    return True


if __name__ == "__main__":
    archive = create_backup()
    rotate()
    verify_restore(archive)
