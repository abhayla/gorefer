import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gorefer.settings")

application = get_wsgi_application()

# Load the datacenter network table at worker boot (not in AppConfig.ready(): that would
# add ~1 s to every manage.py command). Fail open - warm() never raises.
try:
    from apps.events import netranges

    netranges.warm()
except Exception:  # pragma: no cover - belt and braces
    import logging

    logging.getLogger(__name__).exception("netranges warm-up import failed")
