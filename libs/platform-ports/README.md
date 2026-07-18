# am-platform-ports

Extractable SDK: **Protocols + schemas + fakes only**. No Temporal, no vendor SDKs.

```bash
cd libs/platform-ports
pip install -e ".[dev]"
pytest
```

```python
from am_platform_ports.ports.ticket import TicketStore
from am_platform_ports.ports.run import RunStore
from am_platform_ports.fakes.run import FakeRunStore
```

See `docs/agent-platform/` (ADR-001…005).
