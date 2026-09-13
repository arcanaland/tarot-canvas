"""What the library says about catalog downloads"""

DOWNLOAD_TEXT = {
    "installed_toast": "Installed {name}",
    "failed: network": "Network error",
    "failed: http": "Transport error",
    "failed: integrity": "Checksum doesn't match",
    "failed: container": "Zip container is busted",
    "failed: destination exists": "Directory with same name already exists",
    "failed: filesystem": "Internal filesystem error",
    "failed: cancelled": "Cancelled",
}


def failure_text(failure):
    return DOWNLOAD_TEXT[f"failed: {failure.kind.value}"]
