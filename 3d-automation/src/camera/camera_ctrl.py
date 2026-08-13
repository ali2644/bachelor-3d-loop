import os
import subprocess

def list_cameras():
    """List available cameras with names (using v4l2-ctl) or fallback to device paths."""
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True, check=True)
        output = result.stdout
        paths = []
        current_name = None
        for line in output.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('/dev'):
                current_name = stripped
            elif stripped.startswith('/dev'):
                if current_name:
                    paths.append(f"{current_name}: {stripped}")
                    current_name = None
                else:
                    paths.append(f"Unnamed Camera: {stripped}")
        return paths
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to listing device paths
        return [f"/dev/{f}" for f in os.listdir('/dev') if f.startswith('video')]


def get_camera_capabilities(device_path):
    """Return supported formats and available camera controls."""
    formats = subprocess.run(
        ['v4l2-ctl', '-d', device_path, '--list-formats-ext'],
        capture_output=True,
        text=True,
        check=True
    )

    controls = subprocess.run(
        ['v4l2-ctl', '-d', device_path, '-L'],
        capture_output=True,
        text=True,
        check=True
    )

    return (
        "=== Supported Formats ===\n\n"
        + formats.stdout
        + "\n\n=== Camera Controls ===\n\n"
        + controls.stdout
    )


def capture_still(
    device_path,
    output_path,
    width=640,
    height=480,
    pixel_format="mjpeg",
    **controls
):
    """Capture a single frame and save it as an image file."""

    # Apply optional V4L2 camera controls
    if controls:
        ctrl_string = ",".join(
            f"{name}={value}"
            for name, value in controls.items()
        )

        subprocess.run(
            [
                "v4l2-ctl",
                "-d",
                device_path,
                f"--set-ctrl={ctrl_string}"
            ],
            check=True
        )

    # Capture a single frame using ffmpeg
    cmd = [
        "ffmpeg",
        "-y",
        "-video_size", f"{width}x{height}",
        "-f", "v4l2",
        "-input_format", pixel_format,
        "-i", device_path,
        "-vframes", "1",
        output_path
    ]

    subprocess.run(cmd, check=True)


def show_live(
    device_path,
    width=640,
    height=480,
    pixel_format="mjpeg",
    **controls
):
    """Display a live video stream from the camera."""

    # Apply optional V4L2 camera controls
    if controls:
        ctrl_string = ",".join(
            f"{name}={value}"
            for name, value in controls.items()
        )

        subprocess.run(
            [
                "v4l2-ctl",
                "-d",
                device_path,
                f"--set-ctrl={ctrl_string}"
            ],
            check=True
        )

    # Start live preview using ffplay
    cmd = [
        "ffplay",
        "-video_size", f"{width}x{height}",
        "-f", "v4l2",
        "-input_format", pixel_format,
        "-i", device_path
    ]

    subprocess.run(cmd, check=True)