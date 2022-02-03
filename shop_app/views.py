from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import F
import datetime
from .serializers import (
    LoginSerializer, RegistrationSerializer, ProductItemSerializer, BasketSerializer,
    OrderInfoSerializer)
from .models import ProductItem, Basket, Promocode, User, OrderInfo, Cashback
from .tasks import order_created, delivery_email_send_task, send_email_confirmation, send_weekly_notif


class RegistrationAPIView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        user = request.data.get('user', {})
        serializer = RegistrationSerializer(data=user)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_email_confirmation.delay(user.id)
        if user.weekly_discount_notif_required:
            send_weekly_notif.delay(user.id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConfirmEmailAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        user.is_verified = True
        user.save()
        return Response(f"User confirmed: {user.is_verified}")



class LoginAPIView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        user = request.data.get('user', {})
        serializer = LoginSerializer(data=user)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AllProductItemsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        product_items = ProductItem.objects.all()
        serializer = ProductItemSerializer(product_items, many=True)
        return Response(serializer.data)


class UserBasketView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_items_additional_info(self, basket, request):
        result_price = 0
        for item in basket:
            if item.get("image"):
                item['photo_url'] = request.build_absolute_uri(item.get("image"))
            else:
                item['photo_url'] = None

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

        return {'items': list(basket), 'result_price': result_price}

    def get(self, request):
        user_id = request.user.id
        basket = ProductItem.objects.prefetch_related("basket_set").\
            filter(basket__user_id=user_id).\
            values("name", "price", "description", "image", "discount__date_expire",
                   number_of_items=F('basket__number_of_items'),
                   discount_value=F("discount__discount_value"))

        items_info = self.get_items_additional_info(basket, request)
        serializer = BasketSerializer(data=items_info)
        serializer.is_valid(raise_exception=True)

        return Response(serializer.data)

    def put(self, request):
        user = request.user
        old_value = request.data.get("old_number")
        new_value = request.data.get("new_number")
        product_item_id = request.data.get("product_item_id")
        record = Basket.objects.filter(user_id=user.id, product_item_id=product_item_id, number_of_items=old_value).first()
        if record:
            record.number_of_items = new_value
            record.save()
            basket = ProductItem.objects.prefetch_related("basket_set"). \
                filter(basket__user_id=user.id). \
                values("name", "price", "description", "image", "discount__date_expire",
                   number_of_items=F('basket__number_of_items'),
                   discount_value=F("discount__discount_value"))

            items_info = self.get_items_additional_info(basket, request)
            serializer = BasketSerializer(data=items_info)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(status=status.HTTP_400_BAD_REQUEST)


class AddItemInBasketView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user_id = request.user.id
        product_item_id = int(request.data.get("product_item_id"))
        product_item_number = int(request.data.get("product_item_number"))
        product_item = ProductItem.objects.get(id=product_item_id)
        user = User.objects.filter(id=user_id).values("id")
        try:
            Basket.objects.create(product_item=product_item, number_of_items=product_item_number, user_id=user)
            return Response(status=status.HTTP_200_OK)
        except Exception as e:
            return Response(status=status.HTTP_409_CONFLICT)


class DeleteProductItemFromBasket(APIView):
    permission_classes = (IsAuthenticated,)

    def delete(self, request):
        user_id = request.user.id
        user = User.objects.filter(id=user_id).first()
        product_item_id = int(request.data.get("product_item_id"))
        product_item = ProductItem.objects.get(id=product_item_id)
        try:
            Basket.objects.get(product_item=product_item, user_id=user).delete()
        except Exception as exc:
            return Response(status=status.HTTP_409_CONFLICT)

        return Response(status=status.HTTP_200_OK)


class CreateOrderView(APIView):
    permission_classes = (IsAuthenticated,)
    item_info = dict()

    def get_items_info(self, request):
        product_items_dict = request.data.get("product_items", {})
        product_items_ids = product_items_dict.keys()
        product_items = ProductItem.objects.filter(id__in=product_items_ids) \
            .values("id", "name", "price", "description", "discount__discount_value", "discount__date_expire")
        amount_price = 0
        amount_number_of_items = 0
        items = dict()
        for item in product_items:
            item_id = item.get("id")
            number_of_items = product_items_dict.get(str(item_id))
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

            amount_number_of_items += number_of_items
            items[str(item_id)] = number_of_items

        self.items_info = {"items": items, "amount_price": amount_price,
                           "amount_number_of_items": amount_number_of_items}

    def add_promocode_discount_if_required(self, request):
        promocode_name = request.data.get("promocode_name")
        promocode = Promocode.objects.get(name=promocode_name)
        if promocode.allowed_to_sum_with_discounts:
            self.items_info["amount_price"] *= (100 - promocode.discount_value) / 100

    def cashback_processing_if_required(self, request):
        is_required_substract_cashback = bool(request.data.get("substract_cashback"))
        cashback = Cashback.objects.all().first()
        user_cashback_points = request.user.cashback_points
        sub_from_user_cashback = 0
        if cashback and is_required_substract_cashback:
            if user_cashback_points > cashback.sufficient_amount_to_subtract:
                if self.items_info["amount_price"] > user_cashback_points:
                    self.items_info["amount_price"] -= user_cashback_points
                    sub_from_user_cashback = user_cashback_points
                else:
                    sub_from_user_cashback = self.items_info["amount_price"] - 1
                    self.items_info["amount_price"] = 1

        new_cashback_points = user_cashback_points - sub_from_user_cashback
        new_cashback_points += self.items_info["amount_price"] * (100 - cashback.cashback_value) / 100
        request.user.cashback_points = new_cashback_points
        request.user.save()

    def fill_order_info_fields_to_serialize(self, request):
        order_info = request.data.get("order_info")
        order_info["user"] = request.user.id
        order_info["product_items"] = self.items_info["items"]
        order_info["amount_price"] = self.items_info["amount_price"]
        order_info["amount_number_of_items"] = self.items_info["amount_number_of_items"]
        return order_info

    def send_notifications(self, request, order):
        order_created.delay(order.id, request.user.id)
        if order.delivery_notif_required:
            delivery_date = order.delivery_date - datetime.timedelta(hours=order.delivery_notif_in_time)

            delivery_email_send_task.apply_async((request.user.id, order.id), eta=delivery_date)

    @transaction.atomic
    def post(self, request):

        self.get_items_info(request)
        self.add_promocode_discount_if_required(request)
        self.cashback_processing_if_required(request)

        order_info = self.fill_order_info_fields_to_serialize(request)

        serializer = OrderInfoSerializer(data=order_info)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        self.send_notifications(request, order)

        return Response(serializer.data, status=status.HTTP_200_OK)


