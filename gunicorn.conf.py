import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
# Cap at 4 to avoid OOM on PaaS containers where cpu_count() reflects the
# host machine rather than the container's actual memory budget.
_cpu = multiprocessing.cpu_count()
workers = int(os.environ.get('WEB_CONCURRENCY', min(max(2, _cpu), 4)))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = 'gthread'
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))
keepalive = 5
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
forwarded_allow_ips = '*'
