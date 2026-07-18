"""Contract helpers — adapter packages can subclass these later."""


class PortContract:
    """Marker for adapter contract suites."""

    port_name: str = "unknown"
