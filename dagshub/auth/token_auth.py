import datetime
from abc import ABCMeta, abstractmethod
from typing import Any, Dict, Generator, TYPE_CHECKING, Optional

import dateutil.parser
from httpx import Request, Response, Auth

from dagshub.common import config

if TYPE_CHECKING:
    from dagshub.auth.tokens import TokenStorage


class DagshubAuthenticator(Auth):
    """
    This class contains a token + flow on how to re-init the token in case of failure
    """

    def __init__(self, token: "DagshubTokenABC", token_storage: "TokenStorage", host: str):
        self._token = token
        self._token_storage = token_storage
        self._host = host

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        # TODO: failure mode recovery
        yield self._token(request)

    @property
    def token_text(self) -> str:
        return self._token.token_text

    def __call__(self, request):
        """
        Forward the call to the token
        """
        # TODO: NEED TO COME UP WITH A WAY TO RENEGOTIATE HERE SOMEHOW
        # PROBABLY NEED TO CHECK FOR requests' REQUEST HERE
        return self._token(request)


class TokenDeserializationError(Exception):
    ...


class DagshubTokenABC(metaclass=ABCMeta):
    token_type = "NONE"
    priority = 10000  # Decides which token is given out first to the user

    def __call__(self, request: Request) -> Request:
        request.headers["Authorization"] = f"Bearer {self.token_text}"
        return request

    @staticmethod
    @abstractmethod
    def deserialize(values: Dict[str, Any]):
        ...

    @abstractmethod
    def serialize(self) -> Dict[str, Any]:
        ...

    @property
    @abstractmethod
    def token_text(self) -> str:
        ...

    @property
    @abstractmethod
    def is_expired(self) -> bool:
        ...


class OAuthDagshubToken(DagshubTokenABC):
    token_type = "bearer"
    priority = 1

    def __init__(self, token_value: str, expiry_date: datetime.datetime):
        self.token_value = token_value
        self.expiry_date = expiry_date

    # TODO: override the call function to warn about how much lifetime the token has

    def serialize(self) -> Dict[str, Any]:
        return {
            "access_token": self.token_value,
            "expiry": self.expiry_date.isoformat(),
            "token_type": self.token_type,
        }

    @staticmethod
    def deserialize(values: Dict[str, Any]):
        token_value = values["access_token"]
        expiry_date = values["expiry"]
        try:
            expiry_date = dateutil.parser.parse(expiry_date)
        except dateutil.parser.ParserError as ex:
            raise TokenDeserializationError from ex
        return OAuthDagshubToken(token_value, expiry_date)

    @property
    def token_text(self) -> str:
        return self.token_value

    @property
    def is_expired(self) -> bool:
        return self.expiry_date < datetime.datetime.now(tz=self.expiry_date.tzinfo)

    def __repr__(self):
        return f"Dagshub OAuth token, valid until {self.expiry_date}"


class AppDagshubToken(DagshubTokenABC):
    token_type = "app-token"
    priority = 0

    def __init__(self, token_value: str):
        self.token_value = token_value

    def serialize(self) -> Dict[str, Any]:
        return {
            "access_token": self.token_value,
            "expiry": "never",
            "token_type": self.token_type,
        }

    @staticmethod
    def deserialize(values: Dict[str, Any]):
        return AppDagshubToken(values["access_token"])

    @property
    def token_text(self) -> str:
        return self.token_value

    @property
    def is_expired(self) -> bool:
        return False

    def __repr__(self):
        return "Dagshub App token"


class EnvVarDagshubToken(DagshubTokenABC):
    token_type = "env-var"
    priority = -1

    def __init__(self, token_value: str, host: Optional[str] = None):
        self.token_value = token_value
        self.host = host or config.host

    def serialize(self) -> Dict[str, Any]:
        raise RuntimeError("Can't serialize env var token")

    @staticmethod
    def deserialize(values: Dict[str, Any]):
        raise RuntimeError("Can't deserialize env var token")

    @property
    def token_text(self) -> str:
        return self.token_value

    @property
    def is_expired(self) -> bool:
        return False

    def __repr__(self):
        return f"Dagshub Env Var token for host {self.host}"


class HTTPBearerAuth(Auth):
    """Attaches HTTP Bearer Authorization to the given Request object."""

    def __init__(self, token):
        self.token = token

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request

    def __eq__(self, other):
        return all([
            self.token == getattr(other, 'token', None),
        ])

    def __ne__(self, other):
        return not self == other

    def __call__(self, r):
        r.headers['Authorization'] = f'Bearer {self.token}'
        return r
