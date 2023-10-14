from dataclasses import asdict, dataclass

import hug
from converge import settings
from falcon import HTTPError, HTTPForbidden, HTTPNotFound, HTTPUnauthorized
from hug.decorators import wraps

from apphelpers.db.peewee import dbtransaction
from apphelpers.errors import BaseError, InvalidSessionError
from apphelpers.loggers import api_logger
from apphelpers.sessions import SessionDBHandler

if settings.get("HONEYBADGER_API_KEY"):
    from honeybadger import Honeybadger
    from honeybadger.utils import filter_dict


def phony(f):
    return f


def raise_not_found_on_none(f):
    if getattr(f, "not_found_on_none", None) == True:

        @wraps(f)
        def wrapper(*ar, **kw):
            ret = f(*ar, **kw)
            if ret is None:
                raise HTTPNotFound("four o four")
            return ret

        return wrapper
    return f


def notify_honeybadger(honeybadger, error, func, args, kwargs):
    try:
        honeybadger.notify(
            error,
            context={
                "func": func.__name__,
                "args": args,
                "kwargs": filter_dict(kwargs, settings.HB_PARAM_FILTERS),
            },
        )
    finally:
        pass


def honeybadger_wrapper(hb):
    """
    wrapper that executes the function in a try/except
    If an exception occurs, it is first reported to Honeybadger
    """

    def wrapper(f):
        @wraps(f)
        def f_wrapped(*args, **kw):
            try:
                return f(*args, **kw)
            except BaseError as e:
                if e.report:
                    notify_honeybadger(
                        honeybadger=hb, error=e, func=f, args=args, kwargs=kw
                    )
                raise HTTPError(e.code, code=e.code, description=e.msg)

            except Exception as e:
                notify_honeybadger(
                    honeybadger=hb, error=e, func=f, args=args, kwargs=kw
                )
                raise e

        return f_wrapped

    return wrapper


@hug.directive()
def user_id(default=None, request=None, **kwargs):
    return request.context["user"].id


@hug.directive()
def user_name(default=None, request=None, **kwargs):
    return request.context["user"].name


@hug.directive()
def user_email(default=None, request=None, **kwargs):
    return request.context["user"].email


@hug.directive()
def user_groups(default=None, request=None, **kwargs):
    return request.context["user"].groups or tuple()


@hug.directive()
def user_site_groups(default=None, request=None, **kwargs):
    return request.context["user"].site_groups or {}


@hug.directive()
def user_site_ctx(default=None, request=None, **kwargs):
    return request.context["user"].site_ctx


@hug.directive()
def domain(default=None, request=None, **kwargs):
    return request.headers["HOST"]


@hug.directive()
def user_mobile(default=None, request=None, **kwargs):
    return request.context["user"].mobile


@dataclass
class User:
    sid: str = None
    id: int = None
    name: str = None
    groups: tuple = ()
    email: str = None
    mobile: str = None
    site_groups: dict = None
    site_ctx: None = None

    def to_dict(self):
        return asdict(self)

    def __bool__(self):
        return bool(self.id)


def setup_strict_context_setter(sessions):
    def set_context(token):

        uid, groups, name, email, mobile, site_groups, site_ctx = (
            None,
            [],
            "",
            None,
            None,
            {},
            None,
        )

        if token:
            try:
                session = sessions.get(
                    token,
                    [
                        "uid",
                        "name",
                        "groups",
                        "email",
                        "mobile",
                        "site_groups",
                        "site_ctx",
                    ],
                )
                uid, name, groups, email, mobile, site_groups, site_ctx = (
                    session["uid"],
                    session["name"],
                    session["groups"],
                    session["email"],
                    session["mobile"],
                    session["site_groups"],
                    session["site_ctx"],
                )
            except InvalidSessionError:
                raise HTTPUnauthorized("Invalid or expired session")

        return User(
            sid=token,
            id=uid,
            name=name,
            groups=groups,
            email=email,
            mobile=mobile,
            site_groups=site_groups,
            site_ctx=site_ctx,
        )

    return set_context


def setup_context_setter(sessions):
    def set_context(response, request, context, module):
        """
        Only sets context based on session.
        Does not raise any error
        """
        uid, groups, name, email, mobile, site_groups, site_ctx = (
            None,
            [],
            "",
            None,
            None,
            {},
            None,
        )
        token = request.get_header("Authorization")
        if token:
            try:
                session = sessions.get(
                    token,
                    [
                        "uid",
                        "name",
                        "groups",
                        "email",
                        "mobile",
                        "site_groups",
                        "site_ctx",
                    ],
                )
                uid, name, groups, email, mobile, site_groups, site_ctx = (
                    session["uid"],
                    session["name"],
                    session["groups"],
                    session["email"],
                    session["mobile"],
                    session["site_groups"],
                    session["site_ctx"],
                )
                if api_logger:
                    api_logger.info("{} | {} | {}", uid, request.method, request.url)

            except InvalidSessionError:
                pass

        request.context["user"] = User(
            sid=token,
            id=uid,
            name=name,
            groups=groups,
            email=email,
            mobile=mobile,
            site_groups=site_groups,
            site_ctx=site_ctx,
        )

    return set_context


class APIFactory:
    def __init__(self, router, urls_prefix=""):
        self.router = router
        self.db_tr_wrapper = phony
        self.access_wrapper = phony
        self.secure_router = None
        self.multi_site_enabled = False
        self.site_identifier = None
        self.urls_prefix = urls_prefix
        self.honeybadger_wrapper = phony

    def enable_multi_site(self, site_identifier):
        self.multi_site_enabled = True
        self.site_identifier = site_identifier

    def setup_db_transaction(self, db):
        self.db_tr_wrapper = dbtransaction(db)

    def setup_honeybadger_monitoring(self):
        api_key = settings.HONEYBADGER_API_KEY
        if not api_key:
            print("Info: Honeybadger API KEY not found. Honeybadger not set")
            return

        print("Info: Setting up Honeybadger")
        hb = Honeybadger()
        hb.configure(api_key=api_key)
        self.honeybadger_wrapper = honeybadger_wrapper(hb)

    def setup_session_db(self, sessiondb_conn):
        """
        redis_conn_params: dict() with below keys
                           (host, port, password, db)
        """
        self.sessions = SessionDBHandler(sessiondb_conn)
        set_context = setup_context_setter(self.sessions)
        self.router = self.router.http(requires=set_context)
        set_context = setup_strict_context_setter(self.sessions)
        self.secure_router = self.router.http(
            requires=hug.authentication.token(set_context)
        )

        def access_wrapper(f):
            """
            This is the authentication + authorization part
            """
            login_required = getattr(f, "login_required", None)
            any_group_required = getattr(f, "any_group_required", None)
            all_groups_required = getattr(f, "all_groups_required", None)
            groups_forbidden = getattr(f, "groups_forbidden", None)
            authorizer = getattr(f, "authorizer", None)

            if login_required or any_group_required or all_groups_required or groups_forbidden or authorizer:

                @wraps(f)
                def wrapper(request, *args, **kw):

                    user = request.context["user"]

                    # this is authentication part
                    if not user.id:
                        raise HTTPUnauthorized("Invalid or expired session")

                    # this is authorization part
                    groups = set(user.groups)

                    if any_group_required and groups.isdisjoint(any_group_required):
                        raise HTTPForbidden("Unauthorized access")

                    if all_groups_required and not groups.issuperset(all_groups_required):
                        raise HTTPForbidden("Unauthorized access")

                    if groups_forbidden and groups.intersection(groups_forbidden):
                        raise HTTPForbidden("Unauthorized access")

                    if authorizer and not authorizer(user, *args, **kw):
                        raise HTTPForbidden("Unauthorized access")

                    return f(*args, **kw)

            else:
                wrapper = f

            return wrapper

        def multisite_access_wrapper(f):
            """
            This is the authentication + authorization part
            """
            login_required = getattr(f, "login_required", None)
            any_group_required = getattr(f, "any_group_required", None)
            all_groups_required = getattr(f, "all_groups_required", None)
            groups_forbidden = getattr(f, "groups_forbidden", None)
            authorizer = getattr(f, "authorizer", None)

            if login_required or any_group_required or all_groups_required or groups_forbidden or authorizer:

                @wraps(f)
                def wrapper(request, *args, **kw):

                    user = request.context["user"]
                    site_id = (
                        int(kw[self.site_identifier])
                        if self.site_identifier in kw
                        else None
                    )

                    # this is authentication part
                    if not user.id:
                        raise HTTPUnauthorized("Invalid or expired session")

                    # bound site authorization
                    if user.site_ctx and site_id != user.site_ctx:
                        raise HTTPUnauthorized("Invalid or expired session")

                    # this is authorization part
                    groups = set(user.groups)
                    if site_id:
                        groups = groups.union(user.site_groups.get(site_id, []))

                    if any_group_required and groups.isdisjoint(any_group_required):
                        raise HTTPForbidden("Unauthorized access")

                    if all_groups_required and not groups.issuperset(all_groups_required):
                        raise HTTPForbidden("Unauthorized access")

                    if groups_forbidden and groups.intersection(groups_forbidden):
                        raise HTTPForbidden("Unauthorized access")

                    if authorizer and not authorizer(user, *args, **kw):
                        raise HTTPForbidden("Unauthorized access")

                    return f(*args, **kw)

            else:
                wrapper = f

            return wrapper

        self.access_wrapper = (
            multisite_access_wrapper if self.multi_site_enabled else access_wrapper
        )

    def choose_router(self, f):
        login_required = hasattr(f, "login_required") and f.login_required
        return self.secure_router if login_required else self.router

    def build(self, method, method_args, method_kw, f):
        print(
            f"{method_args[0]} [{method.__name__.upper()}] => {f.__module__}:{f.__name__}"
        )
        m = method(*method_args, **method_kw)
        f = self.access_wrapper(
            self.honeybadger_wrapper(self.db_tr_wrapper(raise_not_found_on_none(f)))
        )
        # NOTE: ^ wrapper ordering is important. access_wrapper needs request which
        # others don't. If access_wrapper comes late in the order it won't be passed
        # request parameter.
        return m(f)

    def get(self, path, *a, **k):
        def _wrapper(f):
            router = self.choose_router(f)
            args = (path if path.startswith("/") else (self.urls_prefix + path),) + a
            return self.build(router.get, args, k, f)

        return _wrapper

    def post(self, path, *a, **k):
        def _wrapper(f):
            router = self.choose_router(f)
            args = (path if path.startswith("/") else (self.urls_prefix + path),) + a
            return self.build(router.post, args, k, f)

        return _wrapper

    def put(self, path, *a, **k):
        def _wrapper(f):
            router = self.choose_router(f)
            args = (path if path.startswith("/") else (self.urls_prefix + path),) + a
            return self.build(router.put, args, k, f)

        return _wrapper

    def patch(self, path, *a, **k):
        def _wrapper(f):
            router = self.choose_router(f)
            args = (path if path.startswith("/") else (self.urls_prefix + path),) + a
            return self.build(router.patch, args, k, f)

        return _wrapper

    def delete(self, path, *a, **k):
        def _wrapper(f):
            router = self.choose_router(f)
            args = (path if path.startswith("/") else (self.urls_prefix + path),) + a
            return self.build(router.delete, args, k, f)

        return _wrapper

    def map_resource(self, collection_url, resource=None, handlers=None, id_field="id"):
        if resource:
            raise NotImplementedError("Resource not supported yet")

        resource_url = collection_url + "{" + id_field + "}"
        assert isinstance(handlers, (list, tuple)), "handlers should be list or tuple"
        (
            get_collection,
            add_resource,
            replace_resource,
            get_resource,
            update_resource,
            delete_resource,
        ) = handlers

        if get_collection:
            self.get(collection_url)(get_collection)
        if add_resource:
            self.post(collection_url)(add_resource)
        if replace_resource:
            self.put(resource_url)(replace_resource)
        if get_resource:
            # get_resource_wrapped = get_or_not_found(get_resource)
            self.get(resource_url)(get_resource)
        if update_resource:
            self.patch(resource_url)(update_resource)
        if delete_resource:
            self.delete(resource_url)(delete_resource)
