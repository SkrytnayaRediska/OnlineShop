from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, ProductItem, OrderInfo, Cashback, Promocode
import datetime
import pytz


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=128,
        min_length=8,
        write_only=True
    )

    token = serializers.CharField(max_length=255, read_only=True)

    class Meta:
        model = User
        fields = ['email', 'name', 'surname', 'phone', 'password', 'is_verified', 'token',
                  'weekly_discount_notif_required']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=255)
    password = serializers.CharField(max_length=128, write_only=True)
    token = serializers.CharField(max_length=255, read_only=True)

    def validate(self, data):
        email = data.get('email', None)
        password = data.get('password', None)

        if email is None:
            raise serializers.ValidationError('An email address is required to log in.')

        if password is None:
            raise serializers.ValidationError('A password is required to log in.')

        user = authenticate(username=email, password=password)

        if user is None:
            raise serializers.ValidationError('A user with this email and password was not found.')

        if not user.is_active:
            raise serializers.ValidationError('This user has been deactivated.')

        return {
            'email': user.email,
            'token': user.token
        }


class ProductItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductItem
        fields = ('name', 'price', 'description', 'image')


class ItemForBasketSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    price = serializers.IntegerField()
    description = serializers.CharField(max_length=250)
    number_of_items = serializers.IntegerField()
    discount_value = serializers.IntegerField(allow_null=True)
    discount__date_expire = serializers.DateTimeField(write_only=True, allow_null=True)
    photo_url = serializers.SerializerMethodField() #serializers.CharField(allow_null=True, allow_blank=True)

    def get_photo_url(self, data):
        request = self.context.get("request")
        if data.get("image"):
            photo_url = request.build_absolute_uri(data.get("image"))
        else:
            photo_url = None
        return photo_url


class BasketSerializer(serializers.Serializer):
    result_price = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    def get_items(self, data):
        items = ItemForBasketSerializer(data, many=True, context={"request": self.context.get("request")}).data
        return items

    def get_result_price(self, data):
        result_price = 0
        for item in data:
            '''if item.get("image"):
                item['photo_url'] = request.build_absolute_uri(item.get("image"))
            else:
                item['photo_url'] = None'''

            discount = item.get("discount_value")
            if discount:
                date_exp = item.get("discount__date_expire")
                delta = date_exp - datetime.datetime.now(datetime.timezone.utc)
                if delta.days >= 0 and delta.seconds >= 0:
                    result_price += (item.get("price") * (100 - discount) / 100) * item.get("number_of_items")
                else:
                    result_price += item.get("price") * item.get("number_of_items")
                    item["discount_value"] = 0
            else:
                result_price += item.get("price") * item.get("number_of_items")

        return result_price


class OrderInfoSerializer(serializers.ModelSerializer):
    def run_validation(self, data=None):
        return data

    class Meta:
        model = OrderInfo
        fields = "__all__"

    def create(self, validated_data):
        validated_data["amount_price"] = self.get_amount_price(validated_data)
        validated_data["amount_number_of_items"] = self.get_amount_number_of_items(validated_data)
        validated_data["user"] = self.get_user()
        validated_data.pop("promocode_name")
        validated_data.pop("substract_cashback")

        return OrderInfo.objects.create(**validated_data)

    def get_amount_price(self, data):
        product_items_dict = data.get("product_items")
        product_items_ids = product_items_dict.keys()
        product_items = ProductItem.objects.filter(id__in=product_items_ids) \
            .values("id", "name", "price", "description", "discount__discount_value", "discount__date_expire")
        amount_price = 0
        for item in product_items:
            number_of_items = product_items_dict.get(str(item.get("id")))
            discount = item.get("discount__discount_value")
            price = item.get("price")
            if discount:
                date_exp = item.get("discount__date_expire")
                delta = date_exp - datetime.datetime.now(datetime.timezone.utc)
                if delta.days >= 0:
                    amount_price += (price * (100 - discount) / 100) * number_of_items
                else:
                    amount_price += price * item.getnumber_of_items
                    item.discount__discount_value = 0
            else:
                amount_price += price * number_of_items

        amount_price = self.add_promocode_discount_if_required(self.context.get("request"), amount_price)
        amount_price = self.cashback_processing_if_required(self.context.get("request"), amount_price)

        return amount_price

    def add_promocode_discount_if_required(self, request, amount_price):
        promocode_name = request.data.get("promocode_name")
        promocode = Promocode.objects.get(name=promocode_name)
        if promocode.allowed_to_sum_with_discounts:
            amount_price *= (100 - promocode.discount_value) / 100
        return amount_price

    def cashback_processing_if_required(self, request, amount_price):
        is_required_substract_cashback = bool(request.data.get("substract_cashback"))
        cashback = Cashback.objects.all().first()
        user_cashback_points = request.user.cashback_points
        sub_from_user_cashback = 0
        if cashback and is_required_substract_cashback:
            if user_cashback_points > cashback.sufficient_amount_to_subtract:
                if amount_price > user_cashback_points:
                    amount_price -= user_cashback_points
                    sub_from_user_cashback = user_cashback_points
                else:
                    sub_from_user_cashback = amount_price - 1
                    amount_price = 1

        new_cashback_points = user_cashback_points - sub_from_user_cashback
        new_cashback_points += amount_price * (100 - cashback.cashback_value) / 100
        request.user.cashback_points = new_cashback_points
        request.user.save()

        return amount_price

    def get_amount_number_of_items(self, data):
        return sum(data.get("product_items").values())

    def get_user(self):
        request = self.context.get("request")
        return request.user


