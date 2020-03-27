import json
import logging

import math
import timeit

import typing

from peewee import ModelSelect
from playhouse.shortcuts import model_to_dict
from peewee import *


def get_database_connection():
    # for now it's an sqlite database
    db = SqliteDatabase()
    return db


database = get_database_connection()


class BaseModel(Model):
    class Meta:
        database = database


class Channel(BaseModel):
    claim_id = TextField(column_name='ClaimId', primary_key=True)
    name = TextField(column_name='Name')

    class Meta:
        table_name = 'CHANNEL'


class Comment(BaseModel):
    comment = TextField(column_name='Body')
    channel = ForeignKeyField(
        backref='comments',
        column_name='ChannelId',
        field='claim_id',
        model=Channel,
        null=True
    )
    comment_id = TextField(column_name='CommentId', primary_key=True)
    is_hidden = BooleanField(column_name='IsHidden', constraints=[SQL("DEFAULT FALSE")])
    claim_id = TextField(column_name='LbryClaimId')
    parent = ForeignKeyField(
        column_name='ParentId',
        field='comment_id',
        model='self',
        null=True,
        backref='replies'
    )
    signature = TextField(column_name='Signature', null=True, unique=True)
    signing_ts = TextField(column_name='SigningTs', null=True)
    timestamp = IntegerField(column_name='Timestamp')

    class Meta:
        table_name = 'COMMENT'
        indexes = (
            (('author', 'comment_id'), False),
            (('claim_id', 'comment_id'), False),
        )


FIELDS = {
    'comment': Comment.comment,
    'comment_id': Comment.comment_id,
    'claim_id': Comment.claim_id,
    'timestamp': Comment.timestamp,
    'signature': Comment.signature,
    'signing_ts': Comment.signing_ts,
    'is_hidden': Comment.is_hidden,
    'parent_id': Comment.parent.alias('parent_id'),
    'channel_id': Channel.claim_id.alias('channel_id'),
    'channel_name': Channel.name.alias('channel_name'),
    'channel_url': ('lbry://' + Channel.name + '#' + Channel.claim_id).alias('channel_url')
}


def comment_list(claim_id: str = None, parent_id: str = None,
                 top_level: bool = False, exclude_mode: str = None,
                 page: int = 1, page_size: int = 50, expressions=None,
                 select_fields: list = None, exclude_fields: list = None) -> dict:
    fields = FIELDS.keys()
    if exclude_fields:
        fields -= set(exclude_fields)
    if select_fields:
        fields &= set(select_fields)
    attributes = [FIELDS[field] for field in fields]
    query = Comment.select(*attributes)

    # todo: allow this process to be more automated, so it can just be an expression
    if claim_id:
        query = query.where(Comment.claim_id == claim_id)
        if top_level:
            query = query.where(Comment.parent.is_null())

    if parent_id:
        query = query.where(Comment.ParentId == parent_id)

    if exclude_mode:
        show_hidden = exclude_mode.lower() == 'hidden'
        query = query.where((Comment.is_hidden == show_hidden))

    if expressions:
        query = query.where(expressions)

    total = query.count()
    query = (query
             .join(Channel, JOIN.LEFT_OUTER)
             .order_by(Comment.timestamp.desc())
             .paginate(page, page_size))
    items = [clean(item) for item in query.dicts()]
    # has_hidden_comments is deprecated
    data = {
        'page': page,
        'page_size': page_size,
        'total_pages': math.ceil(total / page_size),
        'total_items': total,
        'items': items,
        'has_hidden_comments': exclude_mode is not None and exclude_mode == 'hidden',
    }
    return data


def clean(thing: dict) -> dict:
    return {k: v for k, v in thing.items() if v is not None}


def get_comment(comment_id: str) -> dict:
    return (comment_list(expressions=(Comment.comment_id == comment_id), page_size=1)
            .get('items')
            .pop())


def get_comment_ids(claim_id: str = None, parent_id: str = None,
                    page: int = 1, page_size: int = 50, flattened=False) -> dict:
    results = comment_list(
        claim_id, parent_id,
        top_level=(parent_id is None),
        page=page, page_size=page_size,
        select_fields=['comment_id', 'parent_id']
    )
    if flattened:
        results.update({
            'items': [item['comment_id'] for item in results['items']],
            'replies': [(item['comment_id'], item.get('parent_id')) for item in results['items']]
        })
    return results


def get_comments_by_id(comment_ids: typing.Union[list, tuple]) -> dict:
    expression = Comment.comment_id.in_(comment_ids)
    return comment_list(expressions=expression, page_size=len(comment_ids))


def get_channel_from_comment_id(comment_id: str) -> dict:
    results = comment_list(
        expressions=(Comment.comment_id == comment_id),
        select_fields=['channel_name', 'channel_id', 'channel_url'],
        page_size=1
    )
    return results['items'].pop()


if __name__ == '__main__':
    logger = logging.getLogger('peewee')
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)

    comments = comment_list(
        page_size=20,
        expressions=((Comment.timestamp < 1583272089) &
                     (Comment.claim_id ** '420%'))
    )

    ids = get_comment_ids('4207d2378bf4340e68c9d88faf7ee24ea1a1f95a')

    print(json.dumps(comments, indent=4))
    print(json.dumps(ids, indent=4))