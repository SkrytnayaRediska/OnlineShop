from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, ProductItem, OrderInfo


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


class BasketSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    price = serializers.IntegerField()
    description = serializers.CharField(max_length=250)
    number_of_items = serializers.IntegerField(source='basket__number_of_items')
    discount = serializers.IntegerField(source="discount__discount_value")
    discount__date_expire = serializers.DateTimeField(write_only=True)
    photo_url = serializers.SerializerMethodField()

    def get_photo_url(self, data):
        request = self.context.get('request')
        photo_url = data["image"]
        if photo_url != "":
            return request.build_absolute_uri(photo_url)
        else:
            return None


class OrderInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderInfo
        fields = ("__all__")

