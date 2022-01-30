from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
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

    def get_total_price_for_products_in_basket(self, basket):
        result_price = 0
        for item in basket:
            discount = item.get("discount__discount_value")

            if discount:
                date_exp = item.get("discount__date_expire")
                delta = date_exp - datetime.datetime.now(datetime.timezone.utc)
                if delta.days >= 0 and delta.seconds >= 0:
                    result_price += (item.get("price") * (100 - discount) / 100) * item.get("basket__number_of_items")
                else:
                    result_price += item.get("price") * item.get("basket__number_of_items")
                    item["discount__discount_value"] = 0
            else:
                result_price += item.get("price") * item.get("basket__number_of_items")

        return basket, result_price

    def get(self, request):
        user_id = request.user.id
        basket = ProductItem.objects.prefetch_related("basket_set").\
            filter(basket__user_id=user_id).\
            values("name", "price", "description", "basket__number_of_items", "discount__discount_value",
                   "discount__date_expire", "image")

        basket, result_price = self.get_total_price_for_products_in_basket(basket)
        serializer = BasketSerializer(basket, many=True, context={"request": request})
        resp = dict()
        resp["items"] = serializer.data
        resp["result_price"] = result_price

        return Response(resp)

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
                values("name", "price", "description", "basket__number_of_items",
                       "discount__discount_value", "discount__date_expire", "image")

            new_basket, result_price = self.get_total_price_for_products_in_basket(basket)
            serializer = BasketSerializer(basket, many=True, context={"request": request})
            resp = dict()
            resp["items"] = serializer.data
            resp["result_price"] = result_price
            return Response(resp, status=status.HTTP_200_OK)
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

    def post(self, request):
        """
        This method:
           1. accepts order-info data from request
           2. calculates amount price with all features like discounts, promocodes and cashback
           3. creates orderinfo record in db
           4. starts celery task for sending notif about order placing
           5. starts celery task for sending notif about delivery
        """

        # ------------------ GET DATA FROM REQUEST --------------------------------------
        user_id = request.user.id
        user = User.objects.filter(id=user_id).first()
        is_required_substract_cashback = bool(request.data.get("substract_cashback"))
        promocode_name = request.data.get("promocode_name")
        delivery_method = request.data.get("delivery_method")
        payment_method = request.data.get("payment_method")
        comment = request.data.get("comment")
        order_date = datetime.date.today()
        delivery_date = request.data.get("delivery_date")
        delivery_date = datetime.datetime.strptime(delivery_date, '%Y-%m-%d %H:%M:%S')\
            .replace(tzinfo=datetime.timezone.utc)
        delivery_address = request.data.get("delivery_address")
        payment_status = "Waiting"
        delivery_status = "In process"
        delivery_notif_required = bool(request.data.get("delivery_notif_required"))
        delivery_notif_in_time = request.data.get("delivery_notif_in_time") if delivery_notif_required else None
        product_items_dict = request.data.get("product_items", {})
        product_items_ids = product_items_dict.keys()
        product_items = ProductItem.objects.filter(id__in=product_items_ids)\
            .values("id", "name", "price", "description", "discount__discount_value", "discount__date_expire")

        # ---------------------- CALCULATE AMOUNT PRICE AND CASHBACK ------------------------
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
                if delta.days >= 0 and delta.seconds >= 0:
                    amount_price += (price * (100 - discount) / 100) * number_of_items
                else:
                    amount_price += price * item.getnumber_of_items
                    item.discount__discount_value = 0
            else:
                amount_price += price * number_of_items

            amount_number_of_items += number_of_items
            items[str(item_id)] = number_of_items

        promocode = Promocode.objects.get(name=promocode_name)
        if promocode.allowed_to_sum_with_discounts:
            amount_price *= (100 - promocode.discount_value) / 100

        cashback = Cashback.objects.all().first()
        user_cashback_points = user.cashback_points
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
        user.cashback_points = new_cashback_points
        user.save()

        # ---------------------- CREATE ORDERINFO RECORD IN DB -----------------------------
        order_info = OrderInfo.objects.create(amount_price=int(amount_price),
                                              amount_number_of_items=amount_number_of_items,
                                              delivery_method=delivery_method,
                                              payment_method=payment_method,
                                              comment=comment,
                                              order_date=order_date,
                                              delivery_date=delivery_date,
                                              payment_status=payment_status,
                                              delivery_status=delivery_status,
                                              delivery_notif_required=delivery_notif_required,
                                              delivery_notif_in_time=delivery_notif_in_time,
                                              delivery_notif_sent=False,
                                              product_items=items,
                                              delivery_address=delivery_address,
                                              user_id=user_id)

        serializer = OrderInfoSerializer(order_info)

        # -------------------- SEND ORDER PLACING NOTIF AND DELIVERY NOTIF --------------------
        order_created.delay(order_info.id, user_id)
        if delivery_notif_required:
            delivery_email_send_task.delay(user_id, order_info.id)
        return Response(serializer.data, status=status.HTTP_200_OK)


