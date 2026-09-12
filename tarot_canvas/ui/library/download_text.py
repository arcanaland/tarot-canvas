"""What the library says about catalog downloads"""

# Adam's prose — every value is a placeholder
DOWNLOAD_TEXT = {
    "installed_toast": "[toast: {name} installed]",
    "failed: network": "[failed: network]",
    "failed: http": "[failed: http]",
    "failed: integrity": "[failed: integrity]",
    "failed: container": "[failed: container]",
    "failed: destination exists": "[failed: destination exists]",
    "failed: filesystem": "[failed: filesystem]",
    "failed: cancelled": "[failed: cancelled]",
}


def failure_text(failure):
    """What a failed download says about its DownloadFailure"""
    return DOWNLOAD_TEXT[f"failed: {failure.kind.value}"]
