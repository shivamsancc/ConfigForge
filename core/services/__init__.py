"""
Application service layer — business logic and orchestration.

Services receive their repository dependencies via constructor injection,
which makes them independently testable: swap the concrete SQLite
repositories for mocks and the service behaves identically from a test's
perspective without touching a real database.

Import pattern::

    from core.services.device_service import DeviceService
    from core.services.generate_service import GenerateService
    # … etc.
"""
