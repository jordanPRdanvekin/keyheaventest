from .._imports import *
class KeyHeavenLogger:
    """Centralized diagnostic logging without hidden filesystem side effects."""

    PREFIX = "[KeyHeaven]"

    @classmethod
    def log_info(cls, message):
        print(f"{cls.PREFIX} [INFO] {message}")

    @classmethod
    def log_warning(cls, message):
        print(f"{cls.PREFIX} [WARNING] {message}")

    @classmethod
    def log_error(cls, context_name, exception, target=None, extra_info=None):
        target_str = f" | Target: '{getattr(target, 'name', 'unknown')}'" if target else ""
        extra_str = f" | Info: {extra_info}" if extra_info else ""
        tb = traceback.format_exc()
        error_msg = (
            f"\n==================== KEYHEAVEN DIAGNOSTIC REPORT ====================\n"
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{cls.PREFIX} [ERROR] Context: {context_name}{target_str}{extra_str}\n"
            f"Exception: {type(exception).__name__} - {exception}\n"
            f"Traceback:\n{tb}"
            f"====================================================================="
        )
        print(error_msg)



class OperationResult:
    """Encapsulates execution metrics, warnings, and errors for operations."""

    def __init__(self, operation_name="Operation"):
        self.operation_name = operation_name
        self.success = True
        self.processed_targets = 0
        self.failed_targets = 0
        self.modified_fcurves = 0
        self.modified_keyframes = 0
        self.skipped_protected = 0
        self.warnings = []
        self.errors = []

    def add_warning(self, msg):
        self.warnings.append(msg)
        KeyHeavenLogger.log_warning(f"[{self.operation_name}] {msg}")

    def add_error(self, msg):
        self.errors.append(msg)
        self.success = False
        KeyHeavenLogger.log_warning(f"[{self.operation_name} ERROR] {msg}")

    def merge(self, other):
        if not other:
            return
        self.success = self.success and other.success
        self.processed_targets += other.processed_targets
        self.failed_targets += other.failed_targets
        self.modified_fcurves += other.modified_fcurves
        self.modified_keyframes += other.modified_keyframes
        self.skipped_protected += other.skipped_protected
        self.warnings.extend(other.warnings)
        self.errors.extend(other.errors)

    def get_summary(self):
        if not self.success and self.processed_targets == 0:
            return f"Failed: {'; '.join(self.errors[:2])}"
        warn_str = f" ({len(self.warnings)} warnings)" if self.warnings else ""
        skipped = (
            f", {self.skipped_protected} protected key(s) skipped"
            if self.skipped_protected
            else ""
        )
        return (
            f"{self.operation_name}: {self.processed_targets} target(s) processed, "
            f"{self.modified_keyframes} key(s) modified{skipped}{warn_str}"
        )
