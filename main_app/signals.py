from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Payment
from .sms_notifications import notify_payment_recorded


@receiver(post_save, sender=Payment)
def sms_on_payment_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        notify_payment_recorded(instance)
    except Exception:
        pass
