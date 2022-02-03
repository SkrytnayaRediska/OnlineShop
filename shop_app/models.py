import jwt
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin
)
from django.db import models


class UserManager(BaseUserManager):

    def create_user(self, email, name, surname, phone, password=None, weekly_discount_notif_required=True):

        if email is None:
            raise TypeError('Users must have an email address.')

        user = self.model(email=self.normalize_email(email))
        user.set_password(password)
        user.name = name
        user.surname = surname
        user.phone = phone
        user.weekly_discount_notif_required = weekly_discount_notif_required
        user.save()

        return user

    def create_superuser(self, email, password):
        if password is None:
            password = "123456789"

        user = self.create_user(email, password=password, name='', surname='', phone='',
                                weekly_discount_notif_required=False)
        user.is_superuser = True
        user.is_staff = True
        user.save()

        return user


class User(AbstractBaseUser, PermissionsMixin):
    username = None
    email = models.EmailField(db_index=True, unique=True)
    name = models.CharField(max_length=50, null=True)
    surname = models.CharField(max_length=50, null=True)
    phone = models.CharField(max_length=20, null=True)
    is_verified = models.BooleanField(default=False)
    weekly_discount_notif_required = models.BooleanField(default=True)
    cashback_points = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def token(self):
        return self._generate_jwt_token()

    def _generate_jwt_token(self):
        dt = datetime.now() + timedelta(days=1)

        token = jwt.encode({
            'id': self.pk,
            'exp': int(dt.strftime('%s'))
        }, settings.SECRET_KEY, algorithm='HS256')

        return token   # .decode('utf-8')


class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Discount(models.Model):
    name = models.CharField(max_length=250)
    discount_value = models.IntegerField()
    date_created = models.DateTimeField()
    date_expire = models.DateTimeField()

    def __str__(self):
        return self.name


class ProductItem(models.Model):
    name = models.CharField(max_length=100)
    price = models.IntegerField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    description = models.CharField(
        max_length=250, default='', blank=True, null=True)
    image = models.ImageField(upload_to='uploads/products/', null=True, default=None, blank=True)
    discount = models.ForeignKey(Discount, on_delete=models.SET_NULL, null=True, default=None, blank=True)

    def __str__(self):
        return self.name


class Promocode(models.Model):
    name = models.CharField(max_length=10, unique=True)
    discount_value = models.IntegerField()
    date_expire = models.DateField()
    allowed_to_sum_with_discounts = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class OrderInfo(models.Model):
    DELIVERY_METHODS = (('Pickup', 'Pickup'), ('Courier', 'Courier'))
    PAYMENT_METHODS = (('Card', 'Card'), ('Cash', 'Cash'))
    DELIVERY_STATUSES = (('In process', 'In process'), ('On the way', 'On the way'),
                         ('Delivered', 'Delivered'))
    PAYMENT_STATUSES = (('Paid', 'Paid'), ('Waiting', 'Waiting for payment'))
    NOTIF_TIME = ((1, 1), (6, 6), (24, 24))

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_items = models.JSONField()
    amount_price = models.FloatField()
    amount_number_of_items = models.IntegerField()
    delivery_method = models.CharField(max_length=10, choices=DELIVERY_METHODS)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    comment = models.TextField(default='')
    order_date = models.DateField()
    delivery_date = models.DateTimeField(null=True, blank=True)
    delivery_address = models.CharField(max_length=500)
    payment_status = models.CharField(max_length=50, choices=PAYMENT_STATUSES)
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUSES)
    delivery_notif_required = models.BooleanField(default=True)
    delivery_notif_in_time = models.IntegerField(choices=NOTIF_TIME, default=0)
    delivery_notif_sent = models.BooleanField(default=False)


class Basket(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_item = models.ForeignKey(ProductItem, on_delete=models.CASCADE)
    number_of_items = models.IntegerField()

    @staticmethod
    def get_basket_by_user_id(user_id):
        return Basket.objects.filter(id_user=user_id)


class Cashback(models.Model):
    cashback_value = models.IntegerField()
    sufficient_amount_to_subtract = models.IntegerField()


