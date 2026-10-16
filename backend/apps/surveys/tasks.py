from celery import shared_task

from . import services


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def broadcast_request(self, request_id: int) -> int:
    return services.broadcast(request_id)


@shared_task
def auto_complete_stale_reviews() -> int:
    return services.auto_complete_stale()
