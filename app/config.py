"""Настройки приложения. Новые флаги по умолчанию выключены — старое поведение не меняется."""

from __future__ import annotations

import os


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


AUTH_ENABLED = _flag("AUTH_ENABLED", "true")
EDIT_LOCKS_ENABLED = _flag("EDIT_LOCKS_ENABLED", "true")
STRUCTURED_RPD_ENABLED = _flag("STRUCTURED_RPD_ENABLED", "true")
ALLOW_SELF_REGISTRATION = _flag("ALLOW_SELF_REGISTRATION")

EXPORT_REQUIRE_VALIDATION = _flag("EXPORT_REQUIRE_VALIDATION", "true")
EXPORT_REQUIRE_REAPPROVAL = _flag("EXPORT_REQUIRE_REAPPROVAL", "false")
EXPORT_FILL_SIGNATURES = _flag("EXPORT_FILL_SIGNATURES", "true")
EXPORT_FILL_REAPPROVAL = _flag("EXPORT_FILL_REAPPROVAL", "true")
# true — DOCX собирается из исходного загруженного файла (инкрементально)
# false — из макета Layout/ (по умолчанию, как на /validation)
EXPORT_USE_ORIGINAL = _flag("EXPORT_USE_ORIGINAL", "false")
# Перед экспортом по макету подхватить правки из templates/tagged|editable (если файл новее)
AUTO_SYNC_USER_TEMPLATE = _flag("AUTO_SYNC_USER_TEMPLATE", "true")

DEFAULT_RPD_TEMPLATE_ID = os.getenv("DEFAULT_RPD_TEMPLATE_ID", "").strip()
DEFAULT_FOS_TEMPLATE_ID = os.getenv("DEFAULT_FOS_TEMPLATE_ID", "").strip()
DEFAULT_RPD_TEMPLATE_NAME = os.getenv("DEFAULT_RPD_TEMPLATE_NAME", "РПД FGOS 3 (макет)")
DEFAULT_FOS_TEMPLATE_NAME = os.getenv("DEFAULT_FOS_TEMPLATE_NAME", "ФОС FGOS 3 (макет)")
DEFAULT_RPP_TEMPLATE_NAME = os.getenv("DEFAULT_RPP_TEMPLATE_NAME", "РПп FGOS 3 (макет)")
DEFAULT_FOSP_TEMPLATE_NAME = os.getenv("DEFAULT_FOSP_TEMPLATE_NAME", "ФОС практика FGOS 3 (макет)")
DEFAULT_GIA_TEMPLATE_NAME = os.getenv("DEFAULT_GIA_TEMPLATE_NAME", "ГИА B3_01 (макет)")
DEFAULT_FOS_GIA_TEMPLATE_NAME = os.getenv(
    "DEFAULT_FOS_GIA_TEMPLATE_NAME", "ФОС ГИА B3_01 (макет)"
)
LAYOUT_DIR = os.getenv("LAYOUT_DIR", "").strip()

PLANS_FOLDER = os.getenv("PLANS_FOLDER", "").strip()


def plans_auto_import() -> bool:
    return _flag("PLANS_AUTO_IMPORT", "true")


def plans_delete_after_import() -> bool:
    return _flag("PLANS_DELETE_AFTER_IMPORT", "true")


def plans_sync_batch_size() -> int:
    return max(1, int(os.getenv("PLANS_SYNC_BATCH_SIZE", "15")))


def plans_sync_on_nav() -> bool:
    """Импорт из папки при каждом открытии дерева (медленно на больших каталогах)."""
    return _flag("PLANS_SYNC_ON_NAV", "false")


def plans_folder_scan_cache_seconds() -> int:
    return max(0, int(os.getenv("PLANS_FOLDER_SCAN_CACHE_SECONDS", "60")))


# Обратная совместимость для прямого импорта констант
PLANS_AUTO_IMPORT = plans_auto_import()
PLANS_DELETE_AFTER_IMPORT = plans_delete_after_import()
PLANS_SYNC_BATCH_SIZE = plans_sync_batch_size()

LOCK_TTL_SECONDS = int(os.getenv("LOCK_TTL_SECONDS", "900"))
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
MAX_ADMIN_USERS = int(os.getenv("MAX_ADMIN_USERS", "2"))
DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")


def max_upload_bytes() -> int:
    """Максимальный размер одного upload-файла (по умолчанию 100 МБ)."""
    return max(1, int(os.getenv("MAX_UPLOAD_MB", "100"))) * 1024 * 1024


def export_retention_hours() -> int:
    """Срок хранения файлов в EXPORTS_DIR (по умолчанию 48 ч)."""
    return max(1, int(os.getenv("EXPORT_RETENTION_HOURS", "48")))


def blocking_io_max_parallel() -> int:
    """Макс. параллельных блокирующих операций (LibreOffice, PDF)."""
    return max(1, int(os.getenv("BLOCKING_IO_MAX_PARALLEL", "2")))


def export_batch_max_parallel() -> int:
    """Макс. параллельных дисциплин в пакетном экспорте направления."""
    return max(1, int(os.getenv("EXPORT_BATCH_MAX_PARALLEL", "3")))


def ai_assistant_enabled() -> bool:
    return _flag("AI_ASSISTANT_ENABLED", "true")


def ai_llm_configured() -> bool:
    return bool(os.getenv("AI_API_KEY", "").strip())
