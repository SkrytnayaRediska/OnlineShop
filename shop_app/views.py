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

    def get(self, request):
        user_id = request.user.id
        basket = ProductItem.objects.prefetch_related("basket_set").\
            filter(basket__user_id=user_id).\
            values("name", "price", "description", "image", "discount__date_expire",
                   number_of_items=F('basket__number_of_items'),
                   discount_value=F("discount__discount_value"))

        serializer = BasketSerializer(basket, context={"request": request})

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

            serializer = BasketSerializer(basket, context={"request": request})
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

    def send_notifications(self, request, order):
        order_created.delay(order.id, request.user.id)
        if bool(order.delivery_notif_required):
            delivery_date = datetime.datetime.strptime(order.delivery_date, "%Y-%m-%d %H:%M:%S") \
                            - datetime.timedelta(hours=order.delivery_notif_in_time)
            delivery_email_send_task.apply_async((request.user.id, order.id), eta=delivery_date)

    @transaction.atomic
    def post(self, request):
        serializer = OrderInfoSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        self.send_notifications(request, order)

        return Response(serializer.data, status=status.HTTP_200_OK)


