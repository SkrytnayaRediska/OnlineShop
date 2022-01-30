from django.contrib import admin
from .models import User, Promocode, ProductItem, Basket, Discount, OrderInfo, Category, Cashback

admin.site.register(Basket)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['phone', 'name', 'surname', 'email', 'is_verified']


@admin.register(ProductItem)
class ProductItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'category', 'discount', 'description']
    list_select_related = ['category', 'discount']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', )


@admin.register(Promocode)
class PromocodeAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Promocode._meta.get_fields()]


@admin.register(OrderInfo)
class OrderInfoAdmin(admin.ModelAdmin):
    list_display = [field.name for field in OrderInfo._meta.get_fields()]


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ['name', 'discount_value', 'date_created', 'date_expire']


@admin.register(Cashback)
class CashbackAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Cashback._meta.get_fields()]
