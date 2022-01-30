from django.urls import path

from .views import (
    LoginAPIView, RegistrationAPIView,
    AllProductItemsView, UserBasketView, AddItemInBasketView, DeleteProductItemFromBasket,
    CreateOrderView, ConfirmEmailAPIView,
)

app_name = 'shop_app'
urlpatterns = [
    path('register', RegistrationAPIView.as_view()),
    path('login', LoginAPIView.as_view()),
    path('all_items', AllProductItemsView.as_view()),
    path('basket', UserBasketView.as_view()),
    path('add_item', AddItemInBasketView.as_view()),
    path('delete_item', DeleteProductItemFromBasket.as_view()),
    path('create_order', CreateOrderView.as_view()),
    path('confirm_email', ConfirmEmailAPIView.as_view()),
    path('update_item_in_basket', UserBasketView.as_view())
]