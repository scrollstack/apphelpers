class BaseError(Exception):

    # Whether to report this error to honeybadger
    report = True

    code = 500
    msg = "Something went wrong"

    def __init__(self, code=None, msg=None):
        self.code = code or self.code
        self.msg = msg or self.msg

    def to_dict(self):
        return {
            "code": self.code,
            "msg": self.msg,
        }


class NotFoundError(BaseError):
    code = 404
    msg = "Not Found"


class AccessDenied(BaseError):
    code = 403
    msg = "Access denied"


class ValidationError(BaseError):
    code = 400
    msg = "Invalid request"


class InvalidSessionError(BaseError):
    code = 401
    msg = "Invalid session"


class ConflictError(BaseError):
    code = 409
    msg = "Duplicate resource"
