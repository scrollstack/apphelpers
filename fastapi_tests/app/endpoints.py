from typing import Optional

from fastapi import Query
from pydantic import BaseModel

from apphelpers.rest import endpoint as ep
from apphelpers.rest.fastapi import json_body, user, user_agent, user_id


def echo(word, user=user):
    return "%s:%s" % (user.id, word) if user else word


async def echo_async(word, user=user):
    return "%s:%s" % (user.id, word) if user else word


def echo_post(data=json_body, user=user):
    return "%s:%s" % (user.id, data) if user else data


@ep.login_required
def secure_echo(word, user=user_id):
    return "%s:%s" % (user.id, word) if user else word


@ep.groups_forbidden("noaccess-group")
@ep.all_groups_required("access-group")
def echo_groups(user=user):
    return user.groups


@ep.groups_forbidden("noaccess-group")
@ep.all_groups_required("access-group")
async def echo_groups_async(user=user):
    return user.groups


def add(nums):
    return sum(int(x) for x in nums)


@ep.login_required
def get_my_uid(body=json_body):
    return body["uid"]


@ep.login_required
@ep.response_model(str)
@ep.not_found_on_none
def get_snake(name=None):
    return name


@ep.login_required
@ep.response_model(str)
@ep.not_found_on_none
async def get_snake_async(name=None):
    return name


@ep.all_groups_required("access-group")
@ep.groups_forbidden("noaccess-group")
def echo_site_groups(site_id: int, user=user):
    return user.site_groups[site_id]


@ep.all_groups_required("access-group")
@ep.groups_forbidden("noaccess-group")
async def echo_site_groups_async(site_id: int, user=user):
    return user.site_groups[site_id]


@ep.login_required
async def echo_user_agent_async(user_agent=user_agent):
    return user_agent


@ep.login_required
@ep.ignore_site_ctx
async def echo_user_agent_without_site_ctx_async(user_agent=user_agent):
    return user_agent


class Fields(BaseModel):
    foo: Optional[int] = None
    bar: Optional[int] = None


@ep.response_model(Fields)
async def get_fields(fields: set = Query(..., default_factory=set)):
    data = {"foo": 1, "bar": None}
    return {k: v for k, v in data.items() if k in fields}


def setup_routes(factory):
    factory.get("/echo/{word}")(echo)
    factory.get("/echo-async/{word}")(echo_async)
    factory.post("/echo")(echo_post)

    factory.get("/add")(add)

    factory.get("/secure-echo/{word}")(secure_echo)
    factory.get("/echo-groups")(echo_groups)
    factory.get("/echo-groups-async")(echo_groups_async)

    factory.post("/me/uid")(get_my_uid)

    factory.get("/snakes/{name}")(get_snake)
    factory.get("/snakes-async/{name}")(get_snake_async)

    factory.get("/sites/{site_id}/echo-groups")(echo_site_groups)
    factory.get("/sites/{site_id}/echo-groups-async")(echo_site_groups_async)

    factory.get("/echo-user-agent-async")(echo_user_agent_async)
    factory.get("/echo-user-agent-without-site-ctx-async")(
        echo_user_agent_without_site_ctx_async
    )
    factory.get("/fields")(get_fields)
