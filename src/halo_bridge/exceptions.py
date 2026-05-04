class HaloBridgeError(Exception):
    """Base exception for halo-bridge."""


class ConfigError(HaloBridgeError):
    """Missing or invalid configuration."""


class HaloAPIError(HaloBridgeError):
    """Error communicating with Halo API."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TargetError(HaloBridgeError):
    """Error publishing to a target platform."""

    def __init__(self, target: str, message: str, status_code: int | None = None):
        super().__init__(f"[{target}] {message}")
        self.target = target
        self.status_code = status_code


class UnknownTargetError(HaloBridgeError):
    """Requested target is not registered."""

    def __init__(self, name: str):
        super().__init__(f"Unknown target: {name}")
        self.name = name
