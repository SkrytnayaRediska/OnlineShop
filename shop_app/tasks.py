from django.core.mail import send_mail
from celery import shared_task
from shop_app.models import User, OrderInfo, ProductItem
from online_shop.settings import EMAIL_HOST_USER
import smtplib
import datetime


WEEKDAY_TO_SEND_ACTUAL_DISCOUNTS_NOTIF = 5   # Saturday


@shared_task
def order_created(order_id, user_id):
    user = User.objects.get(id=user_id)
    subject = 'Order nr. {}'.format(order_id)
    message = 'Dear {},\n\nYou have successfully placed an order.\
                Your order id is {}.'.format(user.name,
                                             order_id)
    mail_sent = send_mail(subject,
                          message,
                          from_email=EMAIL_HOST_USER,
                          recipient_list=['olga@arusnavi.ru',])
    return mail_sent


@shared_task(bind=True, default_retry_delay=60 * 60 * 24)
def send_weekly_notif(self, user_id):
    try:
        today = datetime.datetime.today().weekday()
        if today == WEEKDAY_TO_SEND_ACTUAL_DISCOUNTS_NOTIF:
            discounts = ProductItem.objects.select_related("discount")\
                .filter(discount__date_expire__gte=datetime.datetime.now(datetime.timezone.utc))\
                .values("name", "discount__name")
            user = User.objects.get(id=user_id)
            if discounts:
                email = [user.email]
                subject = 'ACTUAL DISCOUNTS for %s' % user.name
                message = []
                for disc in discounts:
                    message.append(f"{disc.get('discount__name')} for {disc.get('name')}")
                msg = "\n".join(message)
                send_mail(subject, msg, from_email=EMAIL_HOST_USER, recipient_list=email)
                raise Exception
        else:
            raise Exception

    except smtplib.SMTPException as exc:
        print(f"ERROR IN SENDING EMAIL {exc}")


@shared_task
def delivery_email_send_task(user_id, order_id):
    try:
        order = OrderInfo.objects.get(id=order_id)
        user = User.objects.get(id=user_id)
        delivery_notif_sent = order.delivery_notif_sent
        if not delivery_notif_sent:
            email = ["olga@arusnavi.ru"]
            subject = 'Order nr. {}'.format(order_id)
            message = 'Dear {},\n\nYour order will be delivered in {} hours\nDelivery address is {}.'\
                .format(user.name, order.delivery_notif_in_time, order.delivery_address)
            mail_sent = send_mail(subject, message, from_email=EMAIL_HOST_USER, recipient_list=email)
            order.delivery_notif_sent = True
            order.save()
            return mail_sent
    except Exception as exc:
        print(f"EXCEPTION IN DELIVERY NOTIF SENDING: {exc}")


@shared_task
def send_email_confirmation(user_id):
    subject = 'Email Confirmation {}'.format(user_id)
    user = User.objects.get(id=user_id)
    message = 'Confirm your email via this link: {}'.format("http://127.0.0.1:8000/api/confirm_email")
    mail_sent = send_mail(subject,
                          message,
                          from_email=EMAIL_HOST_USER,
                          recipient_list=[user.email])
    return mail_sent
