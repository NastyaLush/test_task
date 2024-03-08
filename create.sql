create type  article_type as enum(
       'WEB',
       'COIN_MARKET_CAP'
);
create table if not exists articles (
    id serial primary key ,
    heading text not null,
    article_type article_type not null ,
    author varchar(50) not null ,
    text text,
    created_at timestamp not null ,
    associated_tokens text not null ,
    link text not null unique
);

