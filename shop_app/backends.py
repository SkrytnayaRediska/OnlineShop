import jwt
from django.conf import settings
from rest_framework import authentication, exceptions
from .models import User


class JWTAuthentication(authentication.BaseAuthentication):
    authentication_header_prefix = 'Bearer'

    def authenticate(self, request):
        request.user = None

        auth_header = authentication.get_authorization_header(request).decode('utf-8')

        #auth_header_prefix = self.authentication_header_prefix.lower()

        if not auth_header:
            return None

        auth_header_token = auth_header.split(" ")

        if len(auth_header_token) < 2:
            return None

        auth_header_token = auth_header_token[1]
        token = auth_header_token

        return self._authenticate_credentials(request, token)

    def _authenticate_credentials(self, request, token):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except Exception as e:
            msg = f"Authentication error. Can't t decode token {e} {token=}"
            raise exceptions.AuthenticationFailed(msg)

        try:
            user = User.objects.get(pk=payload['id'])
        except User.DoesNotExist:
            msg = 'The user corresponding to the token was not found '
            raise exceptions.AuthenticationFailed(msg)

        if not user.is_active:
            msg = 'This user was deactivated'
            raise exceptions.AuthenticationFailed(msg)

        return (user, token)